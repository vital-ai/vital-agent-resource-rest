import logging
import re
from typing import Any, Callable, Optional, Set

from githubkit import GitHub, TokenAuthStrategy
from githubkit.exception import RequestFailed, GitHubException

logger = logging.getLogger("VitalAgentContainerLogger")

# Qualifiers that would let a search query escape the repo allowlist
_SCOPE_QUALIFIER_RE = re.compile(r'\b(repo|org|user):', re.IGNORECASE)

_REPO_RE = re.compile(r'^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$')

DEFAULT_MAX_BODY_CHARS = 4000


class GitHubToolError(Exception):
    """Expected failure (config, allowlist, permission, or GitHub API error).

    These are returned to the caller as structured output with api_error set,
    not raised as tool failures, so the agent can read the reason and correct.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def rate_limit_remaining(response: Any) -> Optional[int]:
    """Pull x-ratelimit-remaining off a githubkit response, if present."""
    try:
        value = response.headers.get('x-ratelimit-remaining')
        return int(value) if value is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def has_next_page(response: Any) -> bool:
    """True if GitHub's Link header advertises another page of results."""
    try:
        link = response.headers.get('link') or ''
    except AttributeError:
        return False
    return 'rel="next"' in link


class GitHubClient:
    """Shared auth and transport for all github_* tools.

    Owns the single githubkit client, the repo allowlist, and the write gates,
    so those checks happen in exactly one place regardless of which tool runs.
    """

    def __init__(self, config: Optional[dict]):
        config = config or {}
        self.config = config

        pat = config.get('pat') or config.get('token')
        self.available = bool(pat)

        # Missing credentials must not take the service down at import time --
        # log it and fail per-request instead.
        if not self.available:
            logger.warning(
                "GitHub tools: no PAT configured (expected {ENV}__TOOL__GITHUB__PAT). "
                "GitHub tools will return a configuration error for every request."
            )

        self.base_url = config.get('api_base_url') or None
        self.max_body_chars = int(config.get('max_body_chars') or DEFAULT_MAX_BODY_CHARS)

        # Writes are allowed by default; this flag is an explicit off-switch.
        self.allow_writes = _as_bool(config.get('allow_writes'), True)
        # High-impact operations stay opt-in.
        self.allow_pr_merge = _as_bool(config.get('allow_pr_merge'), False)
        self.allow_workflow_dispatch = _as_bool(config.get('allow_workflow_dispatch'), False)

        self.allowed_repos: Set[str] = self._parse_allowed_repos(config.get('allowed_repos'))

        if self.available:
            logger.info(
                f"GitHub client initialized (token ...{str(pat)[-4:]}, "
                f"allowed_repos={sorted(self.allowed_repos) or 'NONE - all requests will be denied'}, "
                f"allow_writes={self.allow_writes}, allow_pr_merge={self.allow_pr_merge}, "
                f"allow_workflow_dispatch={self.allow_workflow_dispatch})"
            )

        self.gh: Optional[GitHub] = None
        if self.available:
            kwargs = {}
            if self.base_url:
                kwargs['base_url'] = self.base_url
            self.gh = GitHub(TokenAuthStrategy(pat), **kwargs)

    @staticmethod
    def _parse_allowed_repos(raw: Any) -> Set[str]:
        """Parse the comma-separated allowlist into a lowercase set.

        Malformed entries are logged loudly rather than silently dropped -- a
        typo produces an allowlist that matches nothing, which fails closed but
        is baffling to debug without the log line.
        """
        if not raw:
            return set()

        entries = raw if isinstance(raw, (list, tuple)) else str(raw).split(',')
        allowed = set()
        for entry in entries:
            candidate = str(entry).strip()
            if not candidate:
                continue
            if not _REPO_RE.match(candidate):
                logger.error(
                    f"GitHub tools: ignoring malformed allowed_repos entry {candidate!r} "
                    f"(expected 'owner/repo')"
                )
                continue
            allowed.add(candidate.lower())
        return allowed

    def check_available(self) -> None:
        if not self.available:
            raise GitHubToolError(
                "GitHub tools are not configured: no PAT found. "
                "Set {ENV}__TOOL__GITHUB__PAT in the environment."
            )

    def check_repo(self, owner: str, repo: str) -> str:
        """Validate owner/repo and enforce the allowlist. Returns 'owner/repo'.

        Runs before any network call, so a denied repo costs nothing and leaks
        nothing -- not even whether the repository exists.
        """
        self.check_available()

        owner = (owner or '').strip()
        repo = (repo or '').strip()
        full_name = f"{owner}/{repo}"

        if not _REPO_RE.match(full_name):
            raise GitHubToolError(
                f"Invalid repository {full_name!r}: expected 'owner' and 'repo' to be "
                f"plain GitHub names."
            )

        # Fail closed: an unset allowlist denies everything rather than opening
        # up every repo the token can reach.
        if not self.allowed_repos:
            raise GitHubToolError(
                "No repositories are allowed: {ENV}__TOOL__GITHUB__ALLOWED_REPOS is unset or empty. "
                "Set it to a comma-separated list of 'owner/repo' entries."
            )

        if full_name.lower() not in self.allowed_repos:
            raise GitHubToolError(
                f"Repository '{full_name}' is not in the allowed repository list: "
                f"{', '.join(sorted(self.allowed_repos))}"
            )

        return full_name

    def check_write_allowed(self, operation: str, gate: str = 'allow_writes') -> None:
        """Raise if the gate covering this mutation is off."""
        self.check_available()

        if not self.allow_writes:
            raise GitHubToolError(
                f"Write operations are disabled ({{ENV}}__TOOL__GITHUB__ALLOW_WRITES=false); "
                f"'{operation}' was rejected."
            )

        if gate == 'allow_pr_merge' and not self.allow_pr_merge:
            raise GitHubToolError(
                f"Pull request merges are disabled "
                f"({{ENV}}__TOOL__GITHUB__ALLOW_PR_MERGE=false); '{operation}' was rejected."
            )

        if gate == 'allow_workflow_dispatch' and not self.allow_workflow_dispatch:
            raise GitHubToolError(
                f"Workflow dispatch is disabled "
                f"({{ENV}}__TOOL__GITHUB__ALLOW_WORKFLOW_DISPATCH=false); '{operation}' was rejected."
            )

    @staticmethod
    def scoped_search_query(full_name: str, query: str) -> str:
        """Scope a search query to one repo.

        /search/issues takes a query string rather than a repo path, so unlike
        every other operation the repo is not structurally part of the request.
        Without this the allowlist would not apply to search at all.
        """
        query = (query or '').strip()
        if _SCOPE_QUALIFIER_RE.search(query):
            raise GitHubToolError(
                "Search query may not contain 'repo:', 'org:', or 'user:' qualifiers -- "
                "the repository is set by the owner/repo fields. Remove the qualifier and "
                "pass only the repo-relative part of the query."
            )
        return f"repo:{full_name} {query}".strip()

    async def call(self, func: Callable, *args, context: str = '', **kwargs) -> Any:
        """Invoke a githubkit endpoint, mapping failures to GitHubToolError."""
        self.check_available()
        try:
            response = await func(*args, **kwargs)
        except RequestFailed as e:
            raise self._map_request_failed(e, context)
        except GitHubException as e:
            raise GitHubToolError(f"GitHub request failed{self._suffix(context)}: {e}")

        remaining = rate_limit_remaining(response)
        if remaining is not None and remaining < 100:
            logger.warning(f"GitHub rate limit low: {remaining} requests remaining")
        else:
            logger.debug(f"GitHub rate limit remaining: {remaining}")

        return response

    @staticmethod
    def _suffix(context: str) -> str:
        return f" ({context})" if context else ""

    def _map_request_failed(self, error: RequestFailed, context: str) -> GitHubToolError:
        response = error.response
        status = getattr(response, 'status_code', None)
        suffix = self._suffix(context)

        detail = ''
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get('message', '') or ''
                errors = body.get('errors')
                if errors:
                    detail = f"{detail} {errors}".strip()
        except Exception:
            detail = ''

        if status == 401:
            message = (
                f"GitHub rejected the token (401){suffix}. The PAT is invalid, expired, or "
                f"revoked. {detail}"
            )
        elif status == 403 and rate_limit_remaining(response) == 0:
            reset = None
            try:
                reset = response.headers.get('x-ratelimit-reset')
            except AttributeError:
                pass
            message = (
                f"GitHub rate limit exceeded (403){suffix}. "
                f"Limit resets at epoch {reset}. {detail}"
            )
        elif status == 403:
            message = (
                f"GitHub denied the request (403){suffix}. The token lacks the required scope or "
                f"permission for this operation, or the repository has the feature disabled. {detail}"
            )
        elif status == 404:
            message = (
                f"GitHub returned not found (404){suffix}. Either the resource does not exist, or "
                f"the token cannot see it -- a private repository the PAT lacks access to returns "
                f"404 rather than 403. {detail}"
            )
        elif status == 410:
            message = f"Issues are disabled for this repository (410){suffix}. {detail}"
        elif status == 422:
            message = f"GitHub rejected the request as invalid (422){suffix}. {detail}"
        else:
            message = f"GitHub API error ({status}){suffix}. {detail}"

        logger.error(message.strip())
        return GitHubToolError(message.strip(), status_code=status)
