#!/usr/bin/env python3
"""Offline tests for idempotent create_issue.

No GitHub, no MemoryDB: a stub Redis and a stub GitHub client, so every branch of
the algorithm is reachable including the ones a live test cannot force -- a lost
reservation, an ambiguous timeout, a scan that runs out of budget.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.services import redis_client
from vital_agent_resource_app.services.idempotency import build_key, build_marker
from vital_agent_resource_app.tools.github.github_client import GitHubToolError
from vital_agent_resource_app.tools.github.github_issue_tool import GitHubIssueTool
from vital_agent_resource_app.tools.github.issue_models import GitHubIssueCreateInput

PASSED, FAILED = [], []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


class StubRedis:
    """Enough Redis for the algorithm: SET NX PX, GET, PTTL, DELETE."""

    def __init__(self):
        self.data = {}      # key -> (value, ttl_ms_at_set)
        self.pttl_override = {}

    async def set(self, key, value, nx=False, px=None, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = (value, px or (ex * 1000 if ex else None))
        return True

    async def get(self, key):
        return self.data.get(key, (None, None))[0]

    async def pttl(self, key):
        if key in self.pttl_override:
            return self.pttl_override[key]
        return self.data.get(key, (None, 0))[1] or -1

    async def delete(self, key):
        self.data.pop(key, None)


class StubResponse:
    def __init__(self, payload):
        self._payload = payload
        self.headers = {'x-ratelimit-remaining': '4999'}

    def json(self):
        return self._payload


class StubGitHubClient:
    """Records calls and can be told to fail in a specific way."""

    def __init__(self, fail=None, existing=None):
        self.max_body_chars = 4000
        self.idempotency_enabled = True
        self.idempotency_pending_ttl = 60
        self.idempotency_resolved_ttl = 2592000
        self.idempotency_fail_mode = 'open'
        self.idempotency_pending_grace = 30
        self.creates = []
        self.bodies = []
        self.fail = fail            # GitHubToolError to raise on create
        self.existing = existing or []   # issues the scan should find
        self.gh = self
        self.rest = self
        self.issues = self
        self._next_number = 100

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return self

    def check_repo(self, owner, repo):
        return f"{owner}/{repo}"

    def check_write_allowed(self, *a, **k):
        return None

    async def call(self, func, *args, context='', **kwargs):
        if 'create_issue' in context:
            if self.fail:
                raise self.fail
            data = kwargs.get('data') or {}
            self._next_number += 1
            self.creates.append(data)
            self.bodies.append(data.get('body'))
            return StubResponse({'number': self._next_number, 'title': data.get('title'),
                                 'state': 'open', 'html_url': 'https://example.invalid/1',
                                 'body': data.get('body'), 'labels': [], 'assignees': [],
                                 'comments': 0})
        if 'find_issues_by_body' in context:
            page = kwargs.get('page', 1)
            return StubResponse(self.existing if page == 1 else [])
        if 'read-back' in context:
            number = args[2]
            return StubResponse({'number': number, 'title': 'existing', 'state': 'open',
                                 'html_url': 'https://example.invalid/x', 'body': '',
                                 'labels': [], 'assignees': [], 'comments': 0})
        return StubResponse([])


def make_tool(**kw):
    client = StubGitHubClient(**kw)
    return GitHubIssueTool({}, client), client


def create_input(key='evt-1', **kw):
    params = dict(operation='create_issue', owner='o', repo='r', title='t',
                  idempotency_key=key)
    params.update(kw)
    return GitHubIssueCreateInput(**params)


async def main():
    print("Idempotent create_issue (offline)")
    print("=" * 60)

    print("\n1. Happy path and repeats")
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool()
    out = await tool._create_issue(create_input())
    check('first create files an issue', out.created is True and out.issue is not None)
    check('guard reports memorydb', out.idempotency_guard == 'memorydb',
          str(out.idempotency_guard))
    check('the marker is embedded in the body',
          build_marker('evt-1') in (gh.bodies[0] or ''), str(gh.bodies[0]))

    out2 = await tool._create_issue(create_input())
    check('a repeat does not file a second issue', len(gh.creates) == 1,
          f"{len(gh.creates)} creates")
    check('a repeat reports created=false', out2.created is False, str(out2.created))
    check('a repeat returns the original issue number',
          out2.issue and out2.issue.number == out.issue.number,
          f"{out2.issue.number if out2.issue else None} vs {out.issue.number}")

    print("\n2. No key means no guarantee was asked for")
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool()
    out = await tool._create_issue(GitHubIssueCreateInput(
        operation='create_issue', owner='o', repo='r', title='t'))
    check('guard is null, not "none"', out.idempotency_guard is None, str(out.idempotency_guard))
    check('created is true', out.created is True)
    check('no marker is added without a key',
          '<!-- idempotency-key' not in (gh.bodies[0] or ''), str(gh.bodies[0]))

    print("\n3. Failure handling around the reservation")
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool(fail=GitHubToolError("validation", status_code=422))
    key = build_key('o', 'r', 'evt-4xx')
    try:
        await tool._create_issue(create_input('evt-4xx'))
    except GitHubToolError:
        pass
    check('a definite 4xx releases the reservation', key not in r.data,
          'a blocked key would stall retries for the whole PENDING_TTL')

    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool(fail=GitHubToolError("timed out", status_code=None))
    key = build_key('o', 'r', 'evt-timeout')
    try:
        await tool._create_issue(create_input('evt-timeout'))
    except GitHubToolError:
        pass
    check('an ambiguous timeout retains the reservation', key in r.data,
          'deleting it hands a retry a clean slate for an issue that may exist')

    print("\n4. Concurrent and stale reservations")
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool()
    await r.set(build_key('o', 'r', 'evt-inflight'), 'pending:other', px=60000)
    out = await tool._create_issue(create_input('evt-inflight'))
    check('an in-flight reservation does not create', not gh.creates, str(gh.creates))
    check('an in-flight reservation is explained', 'in flight' in (out.api_error or ''),
          str(out.api_error))

    # Stale reservation, and the scan finds the issue the dead request created.
    r = StubRedis(); redis_client._client = r
    marker = build_marker('evt-stale')
    tool, gh = make_tool(existing=[{'number': 77, 'title': 'earlier', 'state': 'open',
                                    'html_url': 'https://example.invalid/77',
                                    'body': f"text\n{marker}", 'labels': [],
                                    'assignees': [], 'comments': 0}])
    key = build_key('o', 'r', 'evt-stale')
    await r.set(key, 'pending:dead', px=60000)
    r.pttl_override[key] = 1000          # nearly expired -> stale
    out = await tool._create_issue(create_input('evt-stale'))
    check('a stale reservation reconciles against GitHub rather than creating',
          not gh.creates, str(gh.creates))
    check('reconciliation returns the existing issue',
          out.issue and out.issue.number == 77, str(out.issue))
    check('guard reports scan', out.idempotency_guard == 'scan', str(out.idempotency_guard))
    check('the index is repaired', (await r.get(key)) == 'issue:77', str(await r.get(key)))

    # Stale reservation, scan completes and finds nothing -> take over.
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool(existing=[])
    key = build_key('o', 'r', 'evt-stale2')
    await r.set(key, 'pending:dead', px=60000)
    r.pttl_override[key] = 1000
    out = await tool._create_issue(create_input('evt-stale2'))
    check('a completed scan with no match takes over and creates',
          len(gh.creates) == 1 and out.created is True, str(out.created))
    check('guard reports scan for the takeover', out.idempotency_guard == 'scan',
          str(out.idempotency_guard))

    print("\n5. Degraded service")
    redis_client._client = None
    tool, gh = make_tool()
    out = await tool._create_issue(create_input('evt-nored'))
    check('fail-open creates when MemoryDB is absent', out.created is True)
    check('guard reports none', out.idempotency_guard == 'none', str(out.idempotency_guard))
    check('the degraded create says so', 'without an idempotency guarantee' in (out.api_error or ''),
          str(out.api_error))

    tool, gh = make_tool()
    tool.client.idempotency_fail_mode = 'closed'
    try:
        await tool._create_issue(create_input('evt-closed'))
        check('fail-closed refuses to create', False, 'it created anyway')
    except GitHubToolError as e:
        check('fail-closed refuses to create', 'No issue was created' in e.message, e.message[:80])

    tool, gh = make_tool()
    tool.client.idempotency_enabled = False
    try:
        await tool._create_issue(create_input('evt-disabled'))
        check('a key while disabled is an error', False, 'it created anyway')
    except GitHubToolError as e:
        check('a key while disabled is an error', 'disabled' in e.message, e.message[:80])
    check('nothing was created while disabled', not gh.creates, str(gh.creates))

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
