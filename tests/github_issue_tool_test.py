#!/usr/bin/env python3
"""Direct tests for the GitHub issue tool against a scratch repository.

Requires in .env:
    DEV__TOOL__GITHUB__PAT
    DEV__TOOL__GITHUB__ALLOWED_REPOS   (must include the test repo)
    GITHUB_TEST_OWNER / GITHUB_TEST_REPO

Everything this creates in the scratch repo is closed or deleted before exit.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from vital_agent_resource_app.tools.github.github_client import GitHubClient
from vital_agent_resource_app.tools.github.github_issue_tool import GitHubIssueTool
from vital_agent_resource_app.tools.github.issue_models import (
    GitHubIssueListInput, GitHubIssueGetInput, GitHubIssueCreateInput,
    GitHubIssueUpdateInput, GitHubIssueCloseInput, GitHubIssueReopenInput,
    GitHubIssueCommentListInput, GitHubIssueCommentCreateInput,
    GitHubIssueCommentUpdateInput, GitHubIssueCommentDeleteInput,
    GitHubIssueAddLabelsInput, GitHubIssueRemoveLabelsInput,
    GitHubIssueSearchInput,
)
from vital_agent_resource_app.tools.tool_request import ToolRequest


OWNER = os.getenv('GITHUB_TEST_OWNER')
REPO = os.getenv('GITHUB_TEST_REPO')

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = ''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


def build_config():
    return {
        'tool_id': 'github_tool',
        'pat': os.getenv('DEV__TOOL__GITHUB__PAT'),
        'allowed_repos': os.getenv('DEV__TOOL__GITHUB__ALLOWED_REPOS'),
        'allow_writes': os.getenv('DEV__TOOL__GITHUB__ALLOW_WRITES', 'true'),
    }


def build_tool(config_overrides: dict = None):
    config = build_config()
    config.update(config_overrides or {})
    client = GitHubClient(config)
    return GitHubIssueTool(config, client)


async def run(tool, tool_input):
    """Run one operation and return tool_output as a plain dict.

    ToolResponse coerces the output dict into GitHubIssueToolOutput via its
    union, so normalize back to a dict for assertions.
    """
    request = ToolRequest(tool='github_issue_tool', tool_input=tool_input)
    response = await tool.handle_tool_request(request)
    output = response.tool_output
    if output is None:
        return {'api_error': response.error_message}
    return output if isinstance(output, dict) else output.dict()


async def test_lifecycle(tool):
    """create -> get -> comment -> edit comment -> label -> close -> reopen -> cleanup"""
    print("\n1. Issue lifecycle")

    created = await run(tool, GitHubIssueCreateInput(
        operation='create_issue', owner=OWNER, repo=REPO,
        title='[tool test] lifecycle', body='Created by github_issue_tool_test.py',
    ))
    check('create_issue succeeds', created.get('api_error') is None, created.get('api_error'))
    issue = created.get('issue') or {}
    number = issue.get('number')
    check('create_issue returns a number', bool(number), str(created))
    if not number:
        return None

    print(f"     created issue #{number}")

    got = await run(tool, GitHubIssueGetInput(
        operation='get_issue', owner=OWNER, repo=REPO, issue_number=number))
    check('get_issue returns the same issue', (got.get('issue') or {}).get('number') == number,
          str(got.get('api_error')))
    check('get_issue is not flagged as a PR', (got.get('issue') or {}).get('is_pull_request') is False)

    updated = await run(tool, GitHubIssueUpdateInput(
        operation='update_issue', owner=OWNER, repo=REPO, issue_number=number,
        body='Edited body'))
    check('update_issue changes body', (updated.get('issue') or {}).get('body') == 'Edited body',
          str(updated.get('api_error')))
    check('update_issue preserves title',
          (updated.get('issue') or {}).get('title') == '[tool test] lifecycle',
          'title was cleared by a partial update')

    commented = await run(tool, GitHubIssueCommentCreateInput(
        operation='add_comment', owner=OWNER, repo=REPO, issue_number=number,
        body='First comment'))
    comment_id = (commented.get('comment') or {}).get('id')
    check('add_comment returns a comment id', bool(comment_id), str(commented.get('api_error')))

    edited = await run(tool, GitHubIssueCommentUpdateInput(
        operation='update_comment', owner=OWNER, repo=REPO,
        comment_id=comment_id, body='Edited comment'))
    check('update_comment changes body', (edited.get('comment') or {}).get('body') == 'Edited comment',
          str(edited.get('api_error')))

    listed = await run(tool, GitHubIssueCommentListInput(
        operation='list_comments', owner=OWNER, repo=REPO, issue_number=number))
    check('list_comments returns the comment', len(listed.get('comments') or []) == 1,
          str(listed.get('api_error')))

    labeled = await run(tool, GitHubIssueAddLabelsInput(
        operation='add_labels', owner=OWNER, repo=REPO, issue_number=number,
        labels=['bug']))
    check('add_labels applies the label', 'bug' in ((labeled.get('issue') or {}).get('labels') or []),
          str(labeled.get('api_error')))

    unlabeled = await run(tool, GitHubIssueRemoveLabelsInput(
        operation='remove_labels', owner=OWNER, repo=REPO, issue_number=number,
        labels=['bug']))
    check('remove_labels removes the label',
          'bug' not in ((unlabeled.get('issue') or {}).get('labels') or []),
          str(unlabeled.get('api_error')))

    absent = await run(tool, GitHubIssueRemoveLabelsInput(
        operation='remove_labels', owner=OWNER, repo=REPO, issue_number=number,
        labels=['does-not-exist-label']))
    check('remove_labels is idempotent for absent labels', absent.get('api_error') is None,
          str(absent.get('api_error')))

    closed = await run(tool, GitHubIssueCloseInput(
        operation='close_issue', owner=OWNER, repo=REPO, issue_number=number,
        state_reason='not_planned', comment='Closing as a test artifact.'))
    check('close_issue closes the issue', (closed.get('issue') or {}).get('state') == 'closed',
          str(closed.get('api_error')))
    check('close_issue records the reason',
          (closed.get('issue') or {}).get('state_reason') == 'not_planned',
          str((closed.get('issue') or {}).get('state_reason')))
    check('close_issue posts the optional comment', bool(closed.get('comment')))

    reopened = await run(tool, GitHubIssueReopenInput(
        operation='reopen_issue', owner=OWNER, repo=REPO, issue_number=number))
    check('reopen_issue reopens the issue', (reopened.get('issue') or {}).get('state') == 'open',
          str(reopened.get('api_error')))

    deleted = await run(tool, GitHubIssueCommentDeleteInput(
        operation='delete_comment', owner=OWNER, repo=REPO, comment_id=comment_id))
    check('delete_comment succeeds', deleted.get('deleted_id') == comment_id,
          str(deleted.get('api_error')))

    return number


async def test_list_and_search(tool, number):
    print("\n2. List and search")

    # GitHub's issue list index lags behind writes by a second or two, so a
    # just-reopened issue may not appear immediately. Retry rather than race.
    listed = {}
    numbers = []
    for attempt in range(5):
        listed = await run(tool, GitHubIssueListInput(
            operation='list_issues', owner=OWNER, repo=REPO, state='open', max_results=50))
        numbers = [i['number'] for i in (listed.get('issues') or [])]
        if number in numbers:
            break
        await asyncio.sleep(2)

    check('list_issues includes the open test issue', number in numbers,
          f"#{number} not in {numbers} after retries; api_error={listed.get('api_error')}")
    check('list_issues excludes pull requests by default',
          all(i.get('is_pull_request') is False for i in (listed.get('issues') or [])))

    limited = await run(tool, GitHubIssueListInput(
        operation='list_issues', owner=OWNER, repo=REPO, state='all', max_results=1))
    check('max_results caps the result count', len(limited.get('issues') or []) <= 1,
          str(len(limited.get('issues') or [])))

    searched = await run(tool, GitHubIssueSearchInput(
        operation='search_issues', owner=OWNER, repo=REPO, query='is:issue lifecycle'))
    check('search_issues runs and is repo-scoped', searched.get('api_error') is None,
          str(searched.get('api_error')))

    blocked = await run(tool, GitHubIssueSearchInput(
        operation='search_issues', owner=OWNER, repo=REPO,
        query='is:issue org:some-other-org'))
    check('search rejects org: qualifiers',
          blocked.get('api_error') is not None and 'qualifier' in (blocked.get('api_error') or ''),
          str(blocked.get('api_error')))

    blocked_repo = await run(tool, GitHubIssueSearchInput(
        operation='search_issues', owner=OWNER, repo=REPO,
        query='repo:someone/else is:issue'))
    check('search rejects repo: qualifiers', blocked_repo.get('api_error') is not None,
          str(blocked_repo.get('api_error')))


async def test_guards():
    print("\n3. Allowlist and write gates")

    tool = build_tool()
    denied = await run(tool, GitHubIssueListInput(
        operation='list_issues', owner='some-other-org', repo='private-repo'))
    check('repo outside the allowlist is denied',
          denied.get('api_error') is not None and 'not in the allowed' in (denied.get('api_error') or ''),
          str(denied.get('api_error')))

    case_tool = build_tool({'allowed_repos': f"{OWNER.upper()}/{REPO.upper()}"})
    cased = await run(case_tool, GitHubIssueListInput(
        operation='list_issues', owner=OWNER, repo=REPO, max_results=1))
    check('allowlist matching is case-insensitive', cased.get('api_error') is None,
          str(cased.get('api_error')))

    empty_tool = build_tool({'allowed_repos': ''})
    empty = await run(empty_tool, GitHubIssueListInput(
        operation='list_issues', owner=OWNER, repo=REPO))
    check('empty allowlist denies everything (fail closed)',
          empty.get('api_error') is not None and 'No repositories are allowed' in (empty.get('api_error') or ''),
          str(empty.get('api_error')))

    readonly = build_tool({'allow_writes': 'false'})
    blocked = await run(readonly, GitHubIssueCreateInput(
        operation='create_issue', owner=OWNER, repo=REPO, title='should not be created'))
    check('allow_writes=false blocks create_issue',
          blocked.get('api_error') is not None and 'disabled' in (blocked.get('api_error') or ''),
          str(blocked.get('api_error')))

    allowed_read = await run(readonly, GitHubIssueListInput(
        operation='list_issues', owner=OWNER, repo=REPO, max_results=1))
    check('allow_writes=false still permits reads', allowed_read.get('api_error') is None,
          str(allowed_read.get('api_error')))

    unconfigured = GitHubIssueTool({}, GitHubClient({}))
    missing = await run(unconfigured, GitHubIssueListInput(
        operation='list_issues', owner=OWNER, repo=REPO))
    check('missing PAT returns a config error rather than crashing',
          missing.get('api_error') is not None and 'not configured' in (missing.get('api_error') or ''),
          str(missing.get('api_error')))


async def test_validation():
    print("\n4. Input validation and operation routing")

    try:
        ToolRequest(tool='github_issue_tool', tool_input={'operation': 'get_issue', 'repo': REPO})
        check('missing owner is rejected', False, 'no validation error raised')
    except Exception as e:
        check('missing owner is rejected', 'owner' in str(e), str(e)[:120])

    request = ToolRequest(tool='github_issue_tool', tool_input={
        'operation': 'close_issue', 'owner': OWNER, 'repo': REPO, 'issue_number': 1})
    check('operation routes to the right model',
          type(request.tool_input).__name__ == 'GitHubIssueCloseInput',
          type(request.tool_input).__name__)

    reopen = ToolRequest(tool='github_issue_tool', tool_input={
        'operation': 'reopen_issue', 'owner': OWNER, 'repo': REPO, 'issue_number': 1})
    check('close and reopen resolve to different models',
          type(reopen.tool_input).__name__ == 'GitHubIssueReopenInput',
          type(reopen.tool_input).__name__)


async def cleanup(tool, number):
    if not number:
        return
    print("\n5. Cleanup")
    result = await run(tool, GitHubIssueCloseInput(
        operation='close_issue', owner=OWNER, repo=REPO, issue_number=number,
        state_reason='not_planned'))
    check(f'test issue #{number} closed', (result.get('issue') or {}).get('state') == 'closed',
          str(result.get('api_error')))


async def main():
    print("GitHub Issue Tool Test")
    print("=" * 60)

    if not os.getenv('DEV__TOOL__GITHUB__PAT'):
        print("Error: DEV__TOOL__GITHUB__PAT not found in environment")
        return 1
    if not OWNER or not REPO:
        print("Error: GITHUB_TEST_OWNER / GITHUB_TEST_REPO not set")
        return 1

    print(f"Repository: {OWNER}/{REPO}")
    print(f"Allowlist:  {os.getenv('DEV__TOOL__GITHUB__ALLOWED_REPOS')}")

    tool = build_tool()
    number = None
    try:
        number = await test_lifecycle(tool)
        await test_list_and_search(tool, number)
        await test_guards()
        await test_validation()
    finally:
        await cleanup(tool, number)

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for failure in FAILED:
        print(f"  FAILED: {failure}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
