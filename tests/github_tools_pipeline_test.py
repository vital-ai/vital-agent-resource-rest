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

    status, body = call({'operation': 'merge_pr', 'owner': OWNER, 'repo': REPO,
                         'pr_number': number}, tool='github_pr_tool')
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
