#!/usr/bin/env python3
"""
GitHub tools — automated pipeline test (issues, pull requests, actions).

Drives the running service over HTTP and exits non-zero on any failure, so it
can gate a build. Unlike github_issue_tool_client_test.py this does not require
Keycloak: the test stack runs with JWT disabled, and a bearer token is sent only
if TEST_BEARER_TOKEN is set.

Environment:
    TOOL_SERVICE_URL     base URL of the service (default http://localhost:8018)
    GITHUB_TEST_OWNER    scratch repo owner
    GITHUB_TEST_REPO     scratch repo name
    TEST_BEARER_TOKEN    optional JWT, when running against a JWT-enabled stack
    SERVICE_WAIT_SECONDS how long to wait for /health (default 60)
    GITHUB_TEST_ENABLE_DISPATCH  'true' to run the live workflow dispatch checks.
                         Off by default: a run spends Actions minutes, and the
                         stack must also set ALLOW_WORKFLOW_DISPATCH=true.
    GITHUB_TEST_WORKFLOW workflow file to dispatch (default pipeline-smoke.yml)

Exit codes:
    0  all checks passed
    1  one or more checks failed
    2  environment or service not usable (nothing was tested)
"""

import json
import os
import sys
import time

import requests

BASE_URL = os.getenv('TOOL_SERVICE_URL', 'http://localhost:8018').rstrip('/')
OWNER = os.getenv('GITHUB_TEST_OWNER')
REPO = os.getenv('GITHUB_TEST_REPO')
TOKEN = os.getenv('TEST_BEARER_TOKEN')
WAIT_SECONDS = int(os.getenv('SERVICE_WAIT_SECONDS', '60'))
DISPATCH_ENABLED = os.getenv('GITHUB_TEST_ENABLE_DISPATCH', '').lower() == 'true'

HEADERS = {'Content-Type': 'application/json'}
if TOKEN:
    HEADERS['Authorization'] = f'Bearer {TOKEN}'

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}", flush=True)
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}", flush=True)


def wait_for_service():
    """Block until /health answers, so the test does not race the container."""
    deadline = time.time() + WAIT_SECONDS
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                print(f"Service ready at {BASE_URL}")
                return True
            last_error = f"status {response.status_code}"
        except requests.RequestException as e:
            last_error = str(e)
        time.sleep(2)
    print(f"Service at {BASE_URL} never became ready: {last_error}")
    return False


def call(tool_input, expect_status=200, tool='github_issue_tool'):
    """POST one operation to /tool. Returns (status_code, body_dict)."""
    payload = {'tool': tool, 'tool_input': tool_input}
    try:
        response = requests.post(f"{BASE_URL}/tool", json=payload, headers=HEADERS, timeout=60)
    except requests.RequestException as e:
        return 0, {'transport_error': str(e)}

    try:
        body = response.json()
    except ValueError:
        body = {'raw': response.text[:300]}

    if response.status_code != expect_status:
        print(f"    (status {response.status_code}, expected {expect_status}): "
              f"{json.dumps(body)[:200]}")

    return response.status_code, body


def tool_output(body):
    """Extract tool_output, surfacing hard failures rather than hiding them.

    A tool that raises returns success=false with tool_output=null. Returning a
    bare {} for that case makes a crash look identical to an empty result --
    which is exactly how a wrong-kwarg TypeError once passed as "0 jobs found".
    Fold error_message into api_error so assertions see it.
    """
    body = body or {}
    output = body.get('tool_output')
    if output:
        return output
    if body.get('success') is False:
        return {'api_error': f"tool failed: {body.get('error_message')}"}
    return {}


def test_read_operations():
    print("\n1. Read operations")

    status, body = call({'operation': 'list_issues', 'owner': OWNER, 'repo': REPO,
                         'state': 'all', 'max_results': 5})
    out = tool_output(body)
    check('list_issues returns 200', status == 200, f"status={status}")
    check('list_issues has no api_error', out.get('api_error') is None, str(out.get('api_error')))
    check('list_issues reports the repository',
          out.get('repository') == f"{OWNER}/{REPO}", str(out.get('repository')))
    check('list_issues excludes pull requests by default',
          all(i.get('is_pull_request') is False for i in out.get('issues', [])))
    check('response carries rate limit info', out.get('rate_limit_remaining') is not None)
    check('returned_count matches the issues actually returned',
          out.get('returned_count') == len(out.get('issues', [])),
          f"returned_count={out.get('returned_count')} len={len(out.get('issues', []))}")
    check('list operations leave total_count null (GitHub gives no corpus total)',
          out.get('total_count') is None, str(out.get('total_count')))


def test_write_lifecycle():
    print("\n2. Write lifecycle")

    status, body = call({'operation': 'create_issue', 'owner': OWNER, 'repo': REPO,
                         'title': '[pipeline] automated test',
                         'body': 'Created by github_issue_tool_pipeline_test.py'})
    out = tool_output(body)
    number = (out.get('issue') or {}).get('number')
    check('create_issue succeeds', status == 200 and out.get('api_error') is None,
          str(out.get('api_error') or status))
    check('create_issue returns an issue number', bool(number), json.dumps(out)[:200])

    if not number:
        return None

    print(f"     created issue #{number}")

    status, body = call({'operation': 'add_comment', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number, 'body': 'Pipeline comment'})
    out = tool_output(body)
    comment_id = (out.get('comment') or {}).get('id')
    check('add_comment returns a comment id', bool(comment_id), str(out.get('api_error')))

    if comment_id:
        status, body = call({'operation': 'delete_comment', 'owner': OWNER, 'repo': REPO,
                             'comment_id': comment_id})
        out = tool_output(body)
        check('delete_comment succeeds', out.get('deleted_id') == comment_id,
              str(out.get('api_error')))

    status, body = call({'operation': 'get_issue', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number})
    out = tool_output(body)
    check('get_issue reads back the created issue',
          (out.get('issue') or {}).get('number') == number, str(out.get('api_error')))

    return number


def test_guards():
    print("\n3. Guards enforced through the service")

    status, body = call({'operation': 'list_issues', 'owner': 'some-other-org',
                         'repo': 'not-allowed'})
    out = tool_output(body)
    check('repo outside the allowlist is denied',
          'not in the allowed' in (out.get('api_error') or ''), str(out.get('api_error')))

    status, body = call({'operation': 'search_issues', 'owner': OWNER, 'repo': REPO,
                         'query': 'is:issue org:some-other-org'}, expect_status=200)
    out = tool_output(body)
    check('search rejects scope-widening qualifiers',
          'qualifier' in (out.get('api_error') or ''), str(out.get('api_error')))

    # Search must actually return matches, not merely avoid an error -- a silent
    # regression to zero hits (e.g. GitHub requiring advanced_search) would
    # otherwise pass unnoticed.
    status, body = call({'operation': 'search_issues', 'owner': OWNER, 'repo': REPO,
                         'query': 'is:issue pipeline'})
    out = tool_output(body)
    check('search returns matches, not just an empty success',
          len(out.get('issues', [])) > 0,
          f"api_error={out.get('api_error')} issues={len(out.get('issues', []))}")
    check('search returned_count matches the payload',
          out.get('returned_count') == len(out.get('issues', [])),
          f"returned_count={out.get('returned_count')}")
    check('search total_count is GitHub\'s corpus total (>= returned_count)',
          (out.get('total_count') or 0) >= (out.get('returned_count') or 0),
          f"total={out.get('total_count')} returned={out.get('returned_count')}")

    status, body = call({'operation': 'delete_issue', 'owner': OWNER, 'repo': REPO,
                         'issue_number': 1}, expect_status=422)
    check('unknown operation returns 422', status == 422, f"status={status}")
    check('422 names the valid operations',
          'expected one of' in json.dumps(body), json.dumps(body)[:200])

    status, body = call({'operation': 'get_issue', 'repo': REPO, 'issue_number': 1},
                        expect_status=422)
    check('missing owner returns 422', status == 422, f"status={status}")


# ---------------------------------------------------------------------------
# Pull requests
#
# Opening a PR needs a branch with a commit on it, which the tool deliberately
# cannot create -- it has no contents API. The branch is set up here as a
# fixture using the PAT directly, then torn down.
# ---------------------------------------------------------------------------

GH_API = 'https://api.github.com'
PAT = os.getenv('DEV__TOOL__GITHUB__PAT')


def gh_headers():
    return {'Authorization': f'Bearer {PAT}', 'Accept': 'application/vnd.github+json'}


def create_test_branch():
    """Create a branch off the default branch with one new file on it."""
    branch = f"pipeline-test-{int(time.time())}"
    base_url = f"{GH_API}/repos/{OWNER}/{REPO}"

    repo = requests.get(base_url, headers=gh_headers(), timeout=30).json()
    default_branch = repo.get('default_branch', 'main')

    ref = requests.get(f"{base_url}/git/ref/heads/{default_branch}",
                       headers=gh_headers(), timeout=30).json()
    sha = (ref.get('object') or {}).get('sha')
    if not sha:
        print(f"    could not read {default_branch} head: {json.dumps(ref)[:200]}")
        return None, None

    created = requests.post(f"{base_url}/git/refs", headers=gh_headers(), timeout=30,
                            json={'ref': f"refs/heads/{branch}", 'sha': sha})
    if created.status_code >= 300:
        print(f"    could not create branch: {created.text[:200]}")
        return None, None

    import base64
    content = base64.b64encode(
        f"pipeline test file for {branch}\n".encode()).decode()
    put = requests.put(f"{base_url}/contents/pipeline-test-{branch}.txt",
                       headers=gh_headers(), timeout=30,
                       json={'message': f'pipeline test commit on {branch}',
                             'content': content, 'branch': branch})
    if put.status_code >= 300:
        print(f"    could not commit to branch: {put.text[:200]}")
        return None, default_branch

    return branch, default_branch


def delete_test_branch(branch):
    if not branch:
        return
    requests.delete(f"{GH_API}/repos/{OWNER}/{REPO}/git/refs/heads/{branch}",
                    headers=gh_headers(), timeout=30)


def test_list_pagination():
    """max_results is a target: PR filtering must not silently shrink the page."""
    print("\n3b. List pagination")

    status, body = call({'operation': 'list_issues', 'owner': OWNER, 'repo': REPO,
                         'state': 'all', 'max_results': 3})
    out = tool_output(body)
    issues = out.get('issues', [])
    check('list_issues fills max_results despite PR filtering',
          len(issues) == 3, f"asked 3, got {len(issues)} (api_error={out.get('api_error')})")
    check('no pull requests leak into the filtered result',
          all(i.get('is_pull_request') is False for i in issues))
    check('returned_count agrees with the payload',
          out.get('returned_count') == len(issues), str(out.get('returned_count')))

    # list_issues can consume several pages internally, so page+1 is not
    # necessarily the next unseen page. next_page is what the caller must use.
    first_next = out.get('next_page')
    check('truncated results advertise a next_page',
          (first_next is not None) if out.get('truncated') else (first_next is None),
          f"truncated={out.get('truncated')} next_page={first_next}")

    if first_next:
        status, body2 = call({'operation': 'list_issues', 'owner': OWNER, 'repo': REPO,
                              'state': 'all', 'max_results': 3, 'page': first_next})
        out2 = tool_output(body2)
        first_ids = {i['number'] for i in issues}
        second_ids = {i['number'] for i in out2.get('issues', [])}
        # Overlap is permitted by design: next_page can point back at a
        # partly-consumed page, because GitHub cannot resume mid-page and
        # repeating a record is safer than skipping one. What must hold is
        # progress -- the next batch has to contain something new.
        check('following next_page makes progress',
              bool(second_ids - first_ids),
              f"second batch {sorted(second_ids)} added nothing to {sorted(first_ids)}")

    # Single-page operations report next_page on the same contract.
    status, body = call({'operation': 'list_comments', 'owner': OWNER, 'repo': REPO,
                         'issue_number': 1, 'max_results': 100})
    out = tool_output(body)
    check('single-page list_comments has a coherent next_page',
          out.get('next_page') is None or out.get('truncated') is True,
          f"truncated={out.get('truncated')} next_page={out.get('next_page')}")


def test_pagination_no_gaps():
    """Walking next_page must not skip anything.

    Gaps and duplicates are the two failure modes of page-based pagination. The
    duplicate check alone passes cleanly on a gap, which is the more dangerous
    of the two -- a repeated issue is obvious, a missing one is invisible.
    """
    print("\n3c. Pagination completeness")

    status, body = call({'operation': 'list_issues', 'owner': OWNER, 'repo': REPO,
                         'state': 'all', 'max_results': 100})
    out = tool_output(body)
    expected = {i['number'] for i in out.get('issues', [])}
    check('baseline listing returns issues to paginate over',
          len(expected) > 2, f"only {len(expected)} issues in {OWNER}/{REPO}")
    if len(expected) <= 2:
        return

    # Small pages force multi-page accumulation, which is where the slice can
    # discard records the next request would otherwise skip past. Derive the step
    # budget from the data: this repository accumulates test issues, and a fixed
    # cap silently turns "ran out of steps" into "missed issues".
    per_call = 2
    budget = (len(expected) // per_call) + 10
    seen = set()
    page = None
    visited = []
    for _ in range(budget):
        payload = {'operation': 'list_issues', 'owner': OWNER, 'repo': REPO,
                   'state': 'all', 'max_results': per_call}
        if page is not None:
            payload['page'] = page
        status, body = call(payload)
        out = tool_output(body)
        if out.get('api_error'):
            check('pagination walk stays error-free', False, str(out.get('api_error')))
            return

        seen |= {i['number'] for i in out.get('issues', [])}
        visited.append(page or 1)

        if not out.get('truncated'):
            break

        nxt = out.get('next_page')
        check_once = nxt is not None
        if not check_once:
            check('truncated always advertises a next_page', False,
                  f"truncated at page {page or 1} with next_page=None")
            return
        # next_page may point back at a partly-consumed page; that is intended.
        # It must still make progress rather than repeating forever.
        if len(visited) > 2 and visited[-1] == visited[-2] == nxt:
            check('pagination makes progress', False, f"stuck repeating page {nxt}")
            return
        page = nxt

    missing = expected - seen
    check('walking next_page reaches every issue (no gaps)',
          not missing,
          f"missed issues {sorted(missing)} after {len(visited)} of {budget} allowed calls")
    check('the walk visited multiple pages', len(visited) > 1, str(visited))


def test_enumeration_and_metadata():
    """The Phase A additions, and the two silent failures they close."""
    print("\n3d. Enumeration and metadata")

    status, body = call({'operation': 'list_labels', 'owner': OWNER, 'repo': REPO})
    out = tool_output(body)
    names = [l['name'] for l in out.get('labels', [])]
    check('list_labels returns the repository labels', 'bug' in names,
          f"api_error={out.get('api_error')} labels={names}")
    check('list_labels reports returned_count',
          out.get('returned_count') == len(names), str(out.get('returned_count')))

    status, body = call({'operation': 'list_milestones', 'owner': OWNER, 'repo': REPO})
    out = tool_output(body)
    check('list_milestones succeeds even with none defined',
          out.get('api_error') is None, str(out.get('api_error')))

    status, body = call({'operation': 'list_assignable_users', 'owner': OWNER, 'repo': REPO})
    out = tool_output(body)
    users = out.get('assignable_users', [])
    check('list_assignable_users returns logins', len(users) > 0,
          f"api_error={out.get('api_error')} users={users}")

    status, body = call({'operation': 'get_repo', 'owner': OWNER, 'repo': REPO},
                        tool='github_repo_tool')
    out = tool_output(body)
    info = out.get('repository_info') or {}
    check('get_repo returns the default branch', bool(info.get('default_branch')),
          f"api_error={out.get('api_error')} info={info}")
    check('get_repo reports repository visibility', info.get('private') is not None)
    check('get_repo supplies open_issues_count',
          info.get('open_issues_count') is not None, str(info))

    return users


def test_silent_failures_are_now_loud(users):
    """Regressions for the two failures reproduced before Phase A.

    Both used to return a clean success: a bogus assignee assigned nobody, and an
    unknown label silently created a repository label.
    """
    print("\n3e. Silent failures are now reported")

    status, body = call({'operation': 'create_issue', 'owner': OWNER, 'repo': REPO,
                         'title': '[pipeline] write-verification check'})
    out = tool_output(body)
    number = (out.get('issue') or {}).get('number')
    check('created an issue for the write checks', bool(number), str(out.get('api_error')))
    if not number:
        return

    status, body = call({'operation': 'add_assignees', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number,
                         'assignees': ['definitely-not-a-real-user-zzz']})
    out = tool_output(body)
    error = out.get('api_error') or ''
    check('a rejected assignee is reported rather than silently dropped',
          'did not assign' in error, f"api_error={error!r}")
    check('the error names the offending login',
          'definitely-not-a-real-user-zzz' in error, error[:140])
    check('the error points at list_assignable_users',
          'list_assignable_users' in error, error[:140])

    status, body = call({'operation': 'add_labels', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number, 'labels': ['kind/typo-not-real']})
    out = tool_output(body)
    error = out.get('api_error') or ''
    check('an unknown label is rejected before writing',
          'Unknown labels' in error, f"api_error={error!r}")
    check('the rejection lists the valid names', 'bug' in error, error[:160])

    # And the repository must be unchanged -- the point of validating first.
    status, body = call({'operation': 'list_labels', 'owner': OWNER, 'repo': REPO})
    out = tool_output(body)
    names = [l['name'] for l in out.get('labels', [])]
    check('the rejected label was not created on the repository',
          'kind/typo-not-real' not in names, str(names))

    # A real label still works, and a real assignee is accepted.
    status, body = call({'operation': 'add_labels', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number, 'labels': ['bug']})
    out = tool_output(body)
    check('a valid label is still applied',
          'bug' in ((out.get('issue') or {}).get('labels') or []),
          str(out.get('api_error')))

    if users:
        status, body = call({'operation': 'add_assignees', 'owner': OWNER, 'repo': REPO,
                             'issue_number': number, 'assignees': [users[0]]})
        out = tool_output(body)
        check('a valid assignee produces no error', out.get('api_error') is None,
              str(out.get('api_error')))

    # Opting out still allows create-on-write, for callers that want it.
    status, body = call({'operation': 'add_labels', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number, 'labels': ['bug'],
                         'validate_labels': False})
    out = tool_output(body)
    check('validate_labels=false skips validation', out.get('api_error') is None,
          str(out.get('api_error')))

    call({'operation': 'close_issue', 'owner': OWNER, 'repo': REPO,
          'issue_number': number, 'state_reason': 'not_planned'})
    print(f"     closed issue #{number}")


def test_contents_and_refs(users):
    """Phase B: reads, branch creation, content writes, and both new gates.

    Also the end-to-end flow the tools could not previously do at all --
    create_branch -> write file -> open PR, with no raw PAT fixture.
    """
    print("\n3f. Contents and refs")

    status, body = call({'operation': 'get_repo', 'owner': OWNER, 'repo': REPO},
                        tool='github_repo_tool')
    default_branch = ((tool_output(body).get('repository_info')) or {}).get('default_branch')
    check('default branch is known', bool(default_branch), str(default_branch))

    status, body = call({'operation': 'get_file_contents', 'owner': OWNER, 'repo': REPO,
                         'path': 'README.md'}, tool='github_repo_tool')
    out = tool_output(body)
    f = out.get('file') or {}
    check('get_file_contents reads a file',
          f.get('content') is not None and not f.get('is_binary'),
          f"api_error={out.get('api_error')} file={ {k: f.get(k) for k in ('type','size','is_binary')} }")
    check('get_file_contents returns a blob sha', bool(f.get('sha')), str(f.get('sha')))

    status, body = call({'operation': 'get_file_contents', 'owner': OWNER, 'repo': REPO,
                         'path': ''}, expect_status=422, tool='github_repo_tool')
    check('an empty path is rejected by validation', status == 422, f"status={status}")

    status, body = call({'operation': 'list_branches', 'owner': OWNER, 'repo': REPO},
                        tool='github_repo_tool')
    out = tool_output(body)
    names = [b['name'] for b in out.get('branches', [])]
    check('list_branches includes the default branch', default_branch in names, str(names))
    check('the default branch is flagged',
          any(b['name'] == default_branch and b['is_default']
              for b in out.get('branches', [])), str(out.get('branches')))

    status, body = call({'operation': 'list_commits', 'owner': OWNER, 'repo': REPO,
                         'max_results': 5}, tool='github_repo_tool')
    out = tool_output(body)
    check('list_commits returns commits', len(out.get('commits', [])) > 0,
          str(out.get('api_error')))

    # --- the gate that matters most: no committing to the default branch ---
    status, body = call({'operation': 'create_or_update_file', 'owner': OWNER, 'repo': REPO,
                         'path': 'should-never-exist.md', 'content': 'nope',
                         'message': 'should be refused', 'branch': default_branch},
                        tool='github_code_tool')
    out = tool_output(body)
    error = out.get('api_error') or ''
    check('committing to the default branch is refused',
          'default branch' in error and 'ALLOW_DEFAULT_BRANCH_WRITES' in error, error[:160])

    # --- create_branch -> write -> PR, entirely through the tools ---
    branch = f"tool-flow-{int(time.time())}"
    status, body = call({'operation': 'create_branch', 'owner': OWNER, 'repo': REPO,
                         'branch': branch}, tool='github_code_tool')
    out = tool_output(body)
    check('create_branch succeeds', (out.get('branch') or {}).get('name') == branch,
          str(out.get('api_error')))

    path = f"pipeline/{branch}.md"
    status, body = call({'operation': 'create_or_update_file', 'owner': OWNER, 'repo': REPO,
                         'path': path, 'content': 'created by the pipeline test\n',
                         'message': 'pipeline: add a file', 'branch': branch},
                        tool='github_code_tool')
    out = tool_output(body)
    w = out.get('write_result') or {}
    check('create_or_update_file creates a file', w.get('created') is True,
          f"api_error={out.get('api_error')} write_result={w}")
    check('the write reports a commit sha', bool(w.get('commit_sha')), str(w))

    # Updating the same path must resolve the blob sha itself.
    status, body = call({'operation': 'create_or_update_file', 'owner': OWNER, 'repo': REPO,
                         'path': path, 'content': 'updated by the pipeline test\n',
                         'message': 'pipeline: update the file', 'branch': branch},
                        tool='github_code_tool')
    out = tool_output(body)
    w = out.get('write_result') or {}
    check('updating an existing file resolves its sha automatically',
          w.get('created') is False and bool(w.get('commit_sha')),
          f"api_error={out.get('api_error')} write_result={w}")

    status, body = call({'operation': 'compare_refs', 'owner': OWNER, 'repo': REPO,
                         'base': default_branch, 'head': branch}, tool='github_repo_tool')
    out = tool_output(body)
    comp = out.get('comparison') or {}
    check('compare_refs reports the branch is ahead',
          comp.get('status') == 'ahead' and (comp.get('ahead_by') or 0) >= 1, str(comp))
    check('compare_refs lists the changed file',
          any(f.get('filename') == path for f in out.get('files', [])),
          str(out.get('files')))

    # The whole point: create_pr is now reachable from a standing start.
    status, body = call({'operation': 'create_pr', 'owner': OWNER, 'repo': REPO,
                         'title': '[pipeline] opened without a PAT fixture',
                         'head': branch, 'base': default_branch,
                         'body': 'Branch and commit were both made through the tools.'},
                        tool='github_pr_tool')
    out = tool_output(body)
    pr_number = (out.get('pull_request') or {}).get('number')
    check('create_pr is reachable using only tool operations', bool(pr_number),
          str(out.get('api_error')))

    if pr_number:
        call({'operation': 'update_pr', 'owner': OWNER, 'repo': REPO,
              'pr_number': pr_number, 'state': 'closed'}, tool='github_pr_tool')
        print(f"     closed PR #{pr_number}")

    # get_commit: a single commit's own diff, which list_commits/compare_refs do not give.
    status, body = call({'operation': 'list_commits', 'owner': OWNER, 'repo': REPO,
                         'ref': branch, 'max_results': 1}, tool='github_repo_tool')
    head_sha = ((tool_output(body).get('commits') or [{}])[0]).get('sha')
    status, body = call({'operation': 'get_commit', 'owner': OWNER, 'repo': REPO,
                         'ref': head_sha}, tool='github_repo_tool')
    out = tool_output(body)
    check('get_commit returns one commit with its files',
          (out.get('commit') or {}).get('sha') == head_sha and len(out.get('files', [])) >= 1,
          str(out.get('api_error')))

    # request_reviewers: the step the default-branch refusal assumes exists.
    if users:
        status, body = call({'operation': 'request_reviewers', 'owner': OWNER, 'repo': REPO,
                             'pr_number': pr_number, 'reviewers': [users[0]]},
                            tool='github_pr_tool')
        out = tool_output(body)
        # The only assignable user here is the PAT owner, who authored the PR,
        # and GitHub refuses "review cannot be requested from pull request
        # author" with a 422. Requesting successfully and being told why not are
        # both acceptable; silently reporting success with nobody requested is
        # not -- that is the failure mode add_assignees had.
        requested = (out.get('pull_request') or {}).get('requested_reviewers') or []
        check('request_reviewers never reports a silent success',
              bool(requested) or bool(out.get('api_error')),
              f"requested={requested} api_error={out.get('api_error')}")

    status, body = call({'operation': 'request_reviewers', 'owner': OWNER, 'repo': REPO,
                         'pr_number': pr_number}, tool='github_pr_tool')
    out = tool_output(body)
    check('request_reviewers with no reviewers is rejected',
          'at least one' in (out.get('api_error') or ''), str(out.get('api_error')))

    # delete_file: the counterpart create_or_update_file shipped without.
    status, body = call({'operation': 'delete_file', 'owner': OWNER, 'repo': REPO,
                         'path': path, 'message': 'pipeline: remove the file',
                         'branch': branch}, tool='github_code_tool')
    out = tool_output(body)
    d = out.get('delete_result') or {}
    check('delete_file removes a file it created',
          d.get('kind') == 'file' and bool(d.get('commit_sha')),
          f"api_error={out.get('api_error')} delete_result={d}")

    status, body = call({'operation': 'get_file_contents', 'owner': OWNER, 'repo': REPO,
                         'path': path, 'ref': branch}, tool='github_repo_tool')
    out = tool_output(body)
    check('the deleted file is gone', out.get('api_status_code') == 404,
          str(out.get('api_error'))[:120])

    # The split is the control: the read-only tool must not accept a write.
    status, body = call({'operation': 'create_or_update_file', 'owner': OWNER, 'repo': REPO,
                         'path': 'x.md', 'content': 'x', 'message': 'x', 'branch': branch},
                        expect_status=422, tool='github_repo_tool')
    check('github_repo_tool refuses a code write outright', status == 422,
          f"status={status} -- the read-only tool accepted a write operation")

    status, body = call({'operation': 'get_repo', 'owner': OWNER, 'repo': REPO},
                        expect_status=422, tool='github_code_tool')
    check('github_code_tool refuses a read operation', status == 422,
          f"status={status} -- the code tool accepted a read operation")

    # delete_branch: teardown through the tools, so a fixture no longer needs a
    # raw PAT and branches stop accumulating.
    status, body = call({'operation': 'delete_branch', 'owner': OWNER, 'repo': REPO,
                         'branch': branch}, tool='github_code_tool')
    out = tool_output(body)
    check('delete_branch removes the branch',
          (out.get('delete_result') or {}).get('kind') == 'branch',
          str(out.get('api_error')))

    status, body = call({'operation': 'list_branches', 'owner': OWNER, 'repo': REPO,
                         'max_results': 100}, tool='github_repo_tool')
    names = [b['name'] for b in tool_output(body).get('branches', [])]
    check('the deleted branch is gone from the repository', branch not in names, str(names))

    # And the default branch must be refused outright, not merely gated.
    status, body = call({'operation': 'delete_branch', 'owner': OWNER, 'repo': REPO,
                         'branch': default_branch}, tool='github_code_tool')
    out = tool_output(body)
    check('deleting the default branch is refused outright',
          'default branch' in (out.get('api_error') or '')
          and 'not gated' in (out.get('api_error') or ''),
          str(out.get('api_error'))[:160])
    check('the default branch still exists',
          default_branch in names, str(names))


def test_pull_requests():
    print("\n4. Pull requests")

    if not PAT:
        check('PR fixture available', False, 'DEV__TOOL__GITHUB__PAT not set')
        return None, None

    branch, base = create_test_branch()
    if not branch:
        check('PR fixture branch created', False, 'branch/commit setup failed')
        return None, None
    print(f"     fixture branch {branch}")

    status, body = call({'operation': 'create_pr', 'owner': OWNER, 'repo': REPO,
                         'title': '[pipeline] automated PR', 'head': branch, 'base': base,
                         'body': 'Opened by the pipeline test.'}, tool='github_pr_tool')
    out = tool_output(body)
    pr = out.get('pull_request') or {}
    number = pr.get('number')
    check('create_pr succeeds', status == 200 and out.get('api_error') is None,
          str(out.get('api_error') or status))
    check('create_pr returns a PR number', bool(number), json.dumps(out)[:200])
    check('create_pr reports head and base',
          pr.get('head') == branch and pr.get('base') == base,
          f"head={pr.get('head')} base={pr.get('base')}")

    if not number:
        delete_test_branch(branch)
        return None, branch

    print(f"     opened PR #{number}")

    status, body = call({'operation': 'get_pr', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_pr_tool')
    out = tool_output(body)
    check('get_pr reads the PR back', (out.get('pull_request') or {}).get('number') == number,
          str(out.get('api_error')))
    check('get_pr reports it is not merged',
          (out.get('pull_request') or {}).get('merged') is False)

    status, body = call({'operation': 'list_prs', 'owner': OWNER, 'repo': REPO,
                         'state': 'open'}, tool='github_pr_tool')
    out = tool_output(body)
    check('list_prs includes the new PR',
          number in [p['number'] for p in out.get('pull_requests', [])],
          str(out.get('api_error')))

    status, body = call({'operation': 'list_pr_files', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_pr_tool')
    out = tool_output(body)
    files = out.get('files', [])
    check('list_pr_files returns the changed file', len(files) == 1, str(files))
    check('list_pr_files omits patch text by default',
          all(f.get('patch') is None for f in files), 'patch returned without include_patch')

    status, body = call({'operation': 'list_pr_files', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number, 'include_patch': True}, tool='github_pr_tool')
    out = tool_output(body)
    check('include_patch returns patch text',
          any(f.get('patch') for f in out.get('files', [])), str(out.get('api_error')))

    status, body = call({'operation': 'add_pr_comment', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number, 'body': 'Pipeline PR comment'},
                        tool='github_pr_tool')
    out = tool_output(body)
    check('add_pr_comment succeeds', bool((out.get('comment') or {}).get('id')),
          str(out.get('api_error')))

    status, body = call({'operation': 'list_pr_comments', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_pr_tool')
    out = tool_output(body)
    check('list_pr_comments returns the comment', len(out.get('comments', [])) >= 1,
          str(out.get('api_error')))

    # A COMMENT review rides on allow_writes and should go through.
    status, body = call({'operation': 'create_pr_review', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number, 'event': 'COMMENT',
                         'body': 'Pipeline review comment.'}, tool='github_pr_tool')
    out = tool_output(body)
    check('create_pr_review(COMMENT) succeeds', bool((out.get('review') or {}).get('id')),
          str(out.get('api_error')))

    status, body = call({'operation': 'list_pr_reviews', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_pr_tool')
    out = tool_output(body)
    check('list_pr_reviews returns the review', len(out.get('reviews', [])) >= 1,
          str(out.get('api_error')))

    # APPROVE shares the merge gate, which is off in this stack.
    status, body = call({'operation': 'create_pr_review', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number, 'event': 'APPROVE'}, tool='github_pr_tool')
    out = tool_output(body)
    check('create_pr_review(APPROVE) is gated with merges',
          'ALLOW_PR_MERGE' in (out.get('api_error') or ''), str(out.get('api_error')))

    # merge_pr moved to github_code_tool -- merging lands commits.
    status, body = call({'operation': 'merge_pr', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_code_tool')
    out = tool_output(body)
    check('merge_pr is blocked by allow_pr_merge=false',
          'ALLOW_PR_MERGE' in (out.get('api_error') or ''), str(out.get('api_error')))

    status, body = call({'operation': 'create_pr', 'owner': 'some-other-org',
                         'repo': 'not-allowed', 'title': 'x', 'head': 'a', 'base': 'b'},
                        tool='github_pr_tool')
    out = tool_output(body)
    check('PR tool enforces the repo allowlist',
          'not in the allowed' in (out.get('api_error') or ''), str(out.get('api_error')))

    return number, branch


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def test_actions():
    print("\n5. Actions")

    status, body = call({'operation': 'list_workflows', 'owner': OWNER, 'repo': REPO},
                        tool='github_actions_tool')
    out = tool_output(body)
    check('list_workflows returns 200', status == 200, f"status={status}")
    check('list_workflows has no api_error', out.get('api_error') is None,
          str(out.get('api_error')))
    check('list_workflows reports a total_count', out.get('total_count') is not None)

    status, body = call({'operation': 'list_workflow_runs', 'owner': OWNER, 'repo': REPO,
                         'max_results': 5}, tool='github_actions_tool')
    out = tool_output(body)
    check('list_workflow_runs succeeds', out.get('api_error') is None, str(out.get('api_error')))
    check('list_workflow_runs returns a runs list', isinstance(out.get('runs'), list))

    status, body = call({'operation': 'list_workflow_runs', 'owner': OWNER, 'repo': REPO,
                         'branch': 'main', 'status': 'failure'}, tool='github_actions_tool')
    out = tool_output(body)
    check('list_workflow_runs accepts branch and status filters',
          out.get('api_error') is None, str(out.get('api_error')))

    # A run id that cannot exist exercises the 404 message mapping.
    status, body = call({'operation': 'get_workflow_run', 'owner': OWNER, 'repo': REPO,
                         'run_id': 1}, tool='github_actions_tool')
    out = tool_output(body)
    check('get_workflow_run maps 404 to a readable error',
          out.get('api_status_code') == 404 and 'not found' in (out.get('api_error') or '').lower(),
          str(out.get('api_error'))[:120])

    # These assert the gate refuses the call. When the stack is deliberately run
    # with dispatch enabled (the 5b path), the same calls reach GitHub instead,
    # so assert that rather than reporting a false failure.
    if DISPATCH_ENABLED:
        status, body = call({'operation': 'trigger_workflow', 'owner': OWNER, 'repo': REPO,
                             'workflow_id': 'no-such-workflow.yml', 'ref': 'main'},
                            tool='github_actions_tool')
        out = tool_output(body)
        check('trigger_workflow passes the gate when dispatch is enabled',
              'ALLOW_WORKFLOW_DISPATCH' not in (out.get('api_error') or ''),
              str(out.get('api_error'))[:120])
    else:
        status, body = call({'operation': 'trigger_workflow', 'owner': OWNER, 'repo': REPO,
                             'workflow_id': 'ci.yml', 'ref': 'main'}, tool='github_actions_tool')
        out = tool_output(body)
        check('trigger_workflow is blocked by allow_workflow_dispatch=false',
              'ALLOW_WORKFLOW_DISPATCH' in (out.get('api_error') or ''), str(out.get('api_error')))

        status, body = call({'operation': 'rerun_workflow', 'owner': OWNER, 'repo': REPO,
                             'run_id': 1}, tool='github_actions_tool')
        out = tool_output(body)
        check('rerun_workflow shares the dispatch gate',
              'ALLOW_WORKFLOW_DISPATCH' in (out.get('api_error') or ''), str(out.get('api_error')))

    status, body = call({'operation': 'list_workflows', 'owner': 'some-other-org',
                         'repo': 'not-allowed'}, tool='github_actions_tool')
    out = tool_output(body)
    check('actions tool enforces the repo allowlist',
          'not in the allowed' in (out.get('api_error') or ''), str(out.get('api_error')))

    status, body = call({'operation': 'delete_everything', 'owner': OWNER, 'repo': REPO},
                        expect_status=422, tool='github_actions_tool')
    check('actions tool rejects an unknown operation', status == 422, f"status={status}")


def test_actions_dispatch():
    """Trigger a real workflow run and read it back.

    Off unless GITHUB_TEST_ENABLE_DISPATCH=true, because this spends Actions
    minutes on a private repo. The stack must also have
    DEV__TOOL__GITHUB__ALLOW_WORKFLOW_DISPATCH=true or every call here is
    correctly refused by the gate.
    """
    if not DISPATCH_ENABLED:
        print("\n5b. Actions dispatch — SKIPPED "
              "(set GITHUB_TEST_ENABLE_DISPATCH=true to run; costs Actions minutes)")
        return

    print("\n5b. Actions dispatch (live run)")

    workflow = os.getenv('GITHUB_TEST_WORKFLOW', 'pipeline-smoke.yml')
    ref = os.getenv('GITHUB_TEST_REF', 'main')

    status, body = call({'operation': 'list_workflows', 'owner': OWNER, 'repo': REPO},
                        tool='github_actions_tool')
    out = tool_output(body)
    names = [w.get('path', '') for w in out.get('workflows', [])]
    check('the smoke workflow is present',
          any(workflow in n for n in names), str(names))

    before = _newest_run_id(workflow, ref)

    status, body = call({'operation': 'trigger_workflow', 'owner': OWNER, 'repo': REPO,
                         'workflow_id': workflow, 'ref': ref,
                         'inputs': {'message': 'pipeline dispatch check'}},
                        tool='github_actions_tool')
    out = tool_output(body)
    check('trigger_workflow is accepted', out.get('triggered') is True,
          str(out.get('api_error')))
    check('trigger_workflow explains the missing run id',
          'no run id' in (out.get('dispatch_note') or ''), str(out.get('dispatch_note'))[:120])

    run_id = _wait_for_new_run(workflow, ref, before)
    check('a new run appears after dispatch', bool(run_id),
          'no new run id within the wait window')
    if not run_id:
        return

    print(f"     dispatched run {run_id}")

    status, body = call({'operation': 'get_workflow_run', 'owner': OWNER, 'repo': REPO,
                         'run_id': run_id}, tool='github_actions_tool')
    out = tool_output(body)
    run = out.get('run') or {}
    check('get_workflow_run reads the dispatched run', run.get('id') == run_id,
          str(out.get('api_error')))
    check('the run reports event=workflow_dispatch', run.get('event') == 'workflow_dispatch',
          str(run.get('event')))
    check('the run reports the branch', run.get('branch') == ref, str(run.get('branch')))

    status, body = call({'operation': 'list_workflow_runs', 'owner': OWNER, 'repo': REPO,
                         'workflow_id': workflow, 'max_results': 5},
                        tool='github_actions_tool')
    out = tool_output(body)
    check('list_workflow_runs filtered by workflow finds the run',
          run_id in [r['id'] for r in out.get('runs', [])], str(out.get('api_error')))

    completed = _wait_for_completion(run_id)
    check('the run completes', completed is not None, 'run did not finish within the wait window')

    status, body = call({'operation': 'list_run_jobs', 'owner': OWNER, 'repo': REPO,
                         'run_id': run_id}, tool='github_actions_tool')
    out = tool_output(body)
    jobs = out.get('jobs', [])
    check('list_run_jobs returns the smoke job', len(jobs) >= 1, str(out.get('api_error')))
    check('jobs carry step results', bool(jobs and jobs[0].get('steps')),
          json.dumps(jobs[:1])[:200])

    if completed == 'success':
        status, body = call({'operation': 'get_run_logs', 'owner': OWNER, 'repo': REPO,
                             'run_id': run_id, 'max_lines_per_file': 20},
                            tool='github_actions_tool')
        out = tool_output(body)
        logs = out.get('logs', [])
        check('get_run_logs unpacks the archive', len(logs) >= 1, str(out.get('api_error')))
        check('log lines come back as text',
              bool(logs and logs[0].get('lines')), json.dumps(logs[:1])[:200])
        check('the echoed marker appears in the logs',
              any('PIPELINE_SMOKE' in line for log in logs for line in log.get('lines', [])),
              'marker not found in the returned tail')

    # Cancelling a finished run is rejected by GitHub (409); that still proves the
    # call is wired up and the gate lets it through.
    status, body = call({'operation': 'cancel_workflow_run', 'owner': OWNER, 'repo': REPO,
                         'run_id': run_id}, tool='github_actions_tool')
    out = tool_output(body)
    check('cancel_workflow_run reaches GitHub rather than being gated',
          'ALLOW_WORKFLOW' not in (out.get('api_error') or ''), str(out.get('api_error'))[:120])


def _newest_run_id(workflow, ref):
    """Newest run id for this workflow, straight from GitHub (test fixture path)."""
    url = (f"{GH_API}/repos/{OWNER}/{REPO}/actions/workflows/{workflow}/runs"
           f"?branch={ref}&per_page=1")
    try:
        runs = requests.get(url, headers=gh_headers(), timeout=30).json().get('workflow_runs', [])
        return runs[0]['id'] if runs else None
    except Exception:
        return None


def _wait_for_new_run(workflow, ref, before, timeout=90):
    """GitHub creates the run asynchronously after a dispatch; poll for a new id."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = _newest_run_id(workflow, ref)
        if current and current != before:
            return current
        time.sleep(3)
    return None


def _wait_for_completion(run_id, timeout=300):
    """Poll until the run leaves queued/in_progress. Returns the conclusion."""
    deadline = time.time() + timeout
    url = f"{GH_API}/repos/{OWNER}/{REPO}/actions/runs/{run_id}"
    while time.time() < deadline:
        try:
            run = requests.get(url, headers=gh_headers(), timeout=30).json()
            if run.get('status') == 'completed':
                print(f"     run finished: {run.get('conclusion')}")
                return run.get('conclusion')
        except Exception:
            pass
        time.sleep(5)
    return None


def cleanup_pr(number, branch):
    if number:
        print("\n6. Cleanup (pull request)")
        status, body = call({'operation': 'update_pr', 'owner': OWNER, 'repo': REPO,
                             'pr_number': number, 'state': 'closed'}, tool='github_pr_tool')
        out = tool_output(body)
        check(f'PR #{number} closed',
              (out.get('pull_request') or {}).get('state') == 'closed',
              str(out.get('api_error')))
    if branch:
        delete_test_branch(branch)
        print(f"     deleted fixture branch {branch}")


def cleanup(number):
    if not number:
        return
    print("\n7. Cleanup (issue)")
    status, body = call({'operation': 'close_issue', 'owner': OWNER, 'repo': REPO,
                         'issue_number': number, 'state_reason': 'not_planned'})
    out = tool_output(body)
    check(f'issue #{number} closed', (out.get('issue') or {}).get('state') == 'closed',
          str(out.get('api_error')))


def main():
    print("=" * 60)
    print("GitHub Issue Tool — Automated Pipeline Test")
    print("=" * 60)
    print(f"Service:    {BASE_URL}")
    print(f"Repository: {OWNER}/{REPO}")
    print(f"Auth:       {'bearer token' if TOKEN else 'none (JWT disabled)'}")

    if not OWNER or not REPO:
        print("GITHUB_TEST_OWNER / GITHUB_TEST_REPO are not set; nothing to test.")
        return 2

    if not wait_for_service():
        return 2

    number = None
    pr_number = None
    branch = None
    try:
        test_read_operations()
        number = test_write_lifecycle()
        test_guards()
        test_list_pagination()
        test_pagination_no_gaps()
        users = test_enumeration_and_metadata()
        test_silent_failures_are_now_loud(users)
        test_contents_and_refs(users)
        pr_number, branch = test_pull_requests()
        test_actions()
        test_actions_dispatch()
    finally:
        cleanup_pr(pr_number, branch)
        cleanup(number)

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for failure in FAILED:
        print(f"  FAILED: {failure}")
    print("=" * 60)

    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
