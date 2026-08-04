#!/usr/bin/env python3
"""Synthetic pagination tests for github_issue_tool._list_issues.

Offline: no PAT, no network, no sandbox repo. The live suites can only exercise
whatever shape the sandbox happens to have, and the pagination bugs found in
review needed specific shapes -- a page that overshoots max_results, a
PR-dominated page, an exact boundary. Those are constructed here.

The core property under test is completeness: a caller that follows next_page
must eventually see every issue, and must never be told "there is more" without
a way to reach it. Duplicates are permitted by design -- GitHub paginates by
page with no offset, so a partly-consumed page has to be re-read.

Run:  <conda>/bin/python tests/github_pagination_test.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.tools.github.github_issue_tool import (
    GitHubIssueTool, MAX_LIST_PAGES
)
from vital_agent_resource_app.tools.github.issue_models import (
    GitHubIssueListInput, GitHubIssueCommentListInput, GitHubIssueSearchInput,
    GitHubIssueListLabelsInput, GitHubIssueListMilestonesInput,
    GitHubIssueListAssignableUsersInput
)
from vital_agent_resource_app.tools.github.github_pr_tool import GitHubPRTool
from vital_agent_resource_app.tools.github.pr_models import (
    GitHubPRListInput, GitHubPRFilesInput, GitHubPRCommentListInput,
    GitHubPRReviewListInput
)
from vital_agent_resource_app.tools.github.github_actions_tool import GitHubActionsTool
from vital_agent_resource_app.tools.github.actions_models import (
    GitHubActionsListWorkflowsInput, GitHubActionsListRunsInput,
    GitHubActionsListJobsInput, GITHUB_ACTIONS_OPERATION_MODELS
)
from vital_agent_resource_app.tools.github.issue_models import (
    GITHUB_ISSUE_OPERATION_MODELS
)
from vital_agent_resource_app.tools.github.pr_models import GITHUB_PR_OPERATION_MODELS
from vital_agent_resource_app.tools.github.repo_models import GITHUB_REPO_OPERATION_MODELS

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


class FakeResponse:
    def __init__(self, records, has_next):
        self._records = records
        self.headers = {'x-ratelimit-remaining': '4999'}
        if has_next:
            self.headers['link'] = '<https://api.github.com/x?page=2>; rel="next"'

    def json(self):
        return self._records


class FakeClient:
    """Stands in for GitHubClient, serving a scripted repository.

    `records` is a flat string of 'I' (issue) and 'P' (pull request) in the order
    GitHub would return them, e.g. 'IIPPIIII'. Pages are derived from it by
    page/per_page exactly as GitHub does -- the record list is fixed and the page
    size decides the boundaries. Modelling fixed pages instead would invent
    records that disappear at small per_page values.
    """

    def __init__(self, records):
        self.records = records
        self.max_body_chars = 4000
        self.requests = []
        self.gh = self  # _list_issues reaches through client.gh.rest.issues...
        self.rest = self
        self.issues = self

    def __getattr__(self, name):
        # client.gh.rest.<namespace>.<endpoint> has to resolve for every tool.
        # call() intercepts before the endpoint is invoked, so any attribute can
        # answer with the fake itself.
        if name.startswith('_'):
            raise AttributeError(name)
        return self

    def check_repo(self, owner, repo):
        return f"{owner}/{repo}"

    def check_write_allowed(self, *args, **kwargs):
        return None

    @staticmethod
    def scoped_search_query(full_name, query):
        return f"repo:{full_name} {query}".strip()

    async def call(self, func, *args, context='', **kwargs):
        page = kwargs.get('page', 1)
        per_page = kwargs.get('per_page', 30)
        self.requests.append(page)

        start = (page - 1) * per_page
        window = self.records[start:start + per_page]

        payload = []
        for offset, kind in enumerate(window):
            number = start + offset + 1   # stable id: position in the record list
            # A superset of the keys the various mappers read, so one fake can
            # serve issues, comments, PRs, files, reviews, workflows and jobs.
            item = {
                'number': number,
                'id': number,
                'title': f"record {number}",
                'name': f"record {number}",
                'filename': f"file{number}.txt",
                'path': f".github/workflows/w{number}.yml",
                'state': 'open',
                'status': 'completed',
                'conclusion': 'success',
                'body': f"body {number}",
                'html_url': f"https://example.invalid/{number}",
                'user': {'login': 'tester'},
                'labels': [],
                'assignees': [],
                'comments': 0,
                'steps': [],
            }
            if kind == 'P':
                item['pull_request'] = {'url': 'https://example.invalid/pr'}
            payload.append(item)

        has_next = start + per_page < len(self.records)
        return FakeResponse(payload, has_next)


def issue_numbers(records):
    """Ids of the records that are issues, in order."""
    return [i + 1 for i, kind in enumerate(records) if kind == 'I']


async def list_once(records, max_results, page=None):
    client = FakeClient(records)
    tool = GitHubIssueTool({}, client)
    vi = GitHubIssueListInput(
        operation='list_issues', owner='o', repo='r',
        state='all', max_results=max_results, page=page
    )
    return await tool._list_issues(vi)


async def walk(records, max_results, max_steps=60):
    """Follow next_page to exhaustion, as a caller would. Returns ids seen."""
    seen = []
    page = None
    steps = 0
    while steps < max_steps:
        steps += 1
        out = await list_once(records, max_results, page)

        if out.returned_count != len(out.issues):
            return seen, f"returned_count {out.returned_count} != {len(out.issues)}"
        if len(out.issues) > max_results:
            return seen, f"returned {len(out.issues)} > max_results {max_results}"
        if out.truncated and out.next_page is None:
            return seen, f"truncated with next_page=None at page {page or 1}"
        if not out.truncated and out.next_page is not None:
            return seen, f"next_page {out.next_page} set but truncated is False"

        seen.extend(i.number for i in out.issues)

        if not out.truncated:
            return seen, None
        if out.next_page == page and not out.issues:
            return seen, f"no progress: page {page} repeated with no records"
        page = out.next_page
    return seen, f"did not terminate within {max_steps} requests"


async def scenario(name, records, max_results):
    expected = issue_numbers(records)
    seen, error = await walk(records, max_results)

    if error:
        check(f"{name} (max_results={max_results})", False, error)
        return

    missing = [n for n in expected if n not in seen]
    check(f"{name} (max_results={max_results})", not missing,
          f"missed {missing}; expected {expected}, saw {seen}")


class EnvelopeClient(FakeClient):
    """Serves a full page plus a next link, for operations whose payload is an
    envelope ({'total_count': N, '<key>': [...]}) rather than a bare list."""

    def __init__(self, count, key=None):
        super().__init__('I' * count)
        self.key = key

    async def call(self, func, *args, context='', **kwargs):
        response = await super().call(func, *args, **kwargs)
        if self.key:
            response._records = {
                'total_count': len(self.records),
                self.key: response._records,
            }
        return response


async def test_every_list_operation():
    """truncated => next_page must hold for every list operation, in every tool.

    list_pr_reviews and list_run_jobs shipped without page input or next_page,
    so they could report truncated with no way to reach the rest -- the same
    invariant violation fixed in _list_issues, still live in two siblings
    because nothing checked them uniformly.
    """
    print("\n4. truncated => next_page, across every list operation")

    # (label, tool class, input, payload key for envelope responses)
    cases = [
        ('issue.list_issues', GitHubIssueTool,
         GitHubIssueListInput(operation='list_issues', owner='o', repo='r',
                              state='all', max_results=2), None),
        ('issue.list_comments', GitHubIssueTool,
         GitHubIssueCommentListInput(operation='list_comments', owner='o', repo='r',
                                     issue_number=1, max_results=2), None),
        ('issue.search_issues', GitHubIssueTool,
         GitHubIssueSearchInput(operation='search_issues', owner='o', repo='r',
                                query='x', max_results=2), 'items'),
        ('pr.list_prs', GitHubPRTool,
         GitHubPRListInput(operation='list_prs', owner='o', repo='r',
                           max_results=2), None),
        ('pr.list_pr_files', GitHubPRTool,
         GitHubPRFilesInput(operation='list_pr_files', owner='o', repo='r',
                            pr_number=1, max_results=2), None),
        ('pr.list_pr_comments', GitHubPRTool,
         GitHubPRCommentListInput(operation='list_pr_comments', owner='o', repo='r',
                                  pr_number=1, max_results=2), None),
        ('pr.list_pr_reviews', GitHubPRTool,
         GitHubPRReviewListInput(operation='list_pr_reviews', owner='o', repo='r',
                                 pr_number=1, max_results=2), None),
        ('actions.list_workflows', GitHubActionsTool,
         GitHubActionsListWorkflowsInput(operation='list_workflows', owner='o', repo='r',
                                         max_results=2), 'workflows'),
        ('actions.list_workflow_runs', GitHubActionsTool,
         GitHubActionsListRunsInput(operation='list_workflow_runs', owner='o', repo='r',
                                    max_results=2), 'workflow_runs'),
        ('actions.list_run_jobs', GitHubActionsTool,
         GitHubActionsListJobsInput(operation='list_run_jobs', owner='o', repo='r',
                                    run_id=1, max_results=2), 'jobs'),
        ('issue.list_labels', GitHubIssueTool,
         GitHubIssueListLabelsInput(operation='list_labels', owner='o', repo='r',
                                    max_results=2), None),
        ('issue.list_milestones', GitHubIssueTool,
         GitHubIssueListMilestonesInput(operation='list_milestones', owner='o', repo='r',
                                        max_results=2), None),
        ('issue.list_assignable_users', GitHubIssueTool,
         GitHubIssueListAssignableUsersInput(operation='list_assignable_users',
                                             owner='o', repo='r', max_results=2), None),
    ]

    handler_for = {
        'list_issues': '_list_issues', 'list_comments': '_list_comments',
        'search_issues': '_search_issues', 'list_prs': '_list_prs',
        'list_pr_files': '_list_pr_files', 'list_pr_comments': '_list_pr_comments',
        'list_pr_reviews': '_list_pr_reviews',
        'list_workflows': '_list_workflows', 'list_workflow_runs': '_list_runs',
        'list_run_jobs': '_list_jobs', 'list_labels': '_list_labels',
        'list_milestones': '_list_milestones',
        'list_assignable_users': '_list_assignable_users',
    }

    # Structural check first. It is derived from the operation registries rather
    # than the table below, so an operation added later is covered whether or not
    # anyone remembers to list it here -- the hand-maintained table is the same
    # per-operation growth pattern that let two unpaginable operations survive.
    # The heuristic is exact against the current code: an input model with
    # max_results returns a collection, and a collection must be resumable.
    registries = {
        'issue': GITHUB_ISSUE_OPERATION_MODELS,
        'pr': GITHUB_PR_OPERATION_MODELS,
        'actions': GITHUB_ACTIONS_OPERATION_MODELS,
        'repo': GITHUB_REPO_OPERATION_MODELS,
    }
    collection_ops = []
    for tool_name, registry in registries.items():
        for operation, model in registry.items():
            if 'max_results' in model.model_fields:
                collection_ops.append(f"{tool_name}.{operation}")
                check(f'{tool_name}.{operation}: returns a collection, so accepts page',
                      'page' in model.model_fields,
                      f"{model.__name__} has no page field, so nothing can be resumed")

    # It must also run before the behavioural loop: that loop reads vi.page, so a
    # model missing the field dies there with an AttributeError instead of the
    # diagnostic above.
    check('every collection operation is exercised behaviourally too',
          {c for c in collection_ops} == {label for label, _, _, _ in cases},
          f"registry says {sorted(collection_ops)}, table covers "
          f"{sorted(label for label, _, _, _ in cases)}")

    for label, tool_cls, vi, key in cases:
        # 6 records at max_results=2 means more always remain.
        client = EnvelopeClient(6, key)
        tool = tool_cls({}, client)
        out = await getattr(tool, handler_for[vi.operation])(vi)

        if not out.truncated:
            check(f'{label}: reports truncated when more remain', False,
                  f"truncated={out.truncated} returned={out.returned_count}")
            continue
        check(f'{label}: truncated implies next_page',
              out.next_page is not None,
              'truncated=True with next_page=None -- the rest is unreachable')


async def main():
    print("Synthetic pagination tests for the GitHub tools")
    print("=" * 62)
    print(f"MAX_LIST_PAGES = {MAX_LIST_PAGES}")

    print("\n1. Shapes the sandbox cannot produce")

    # The exact shape from the round-3 report: page 1 part PRs, page 2 all
    # issues, so the accumulated batch overshoots and the slice discards.
    await scenario('overshoot discards a partly-read page', 'IIPPIIII', 3)
    await scenario('overshoot on the final page', 'IIPPIIII', 5)

    # PR-dominated: filtering empties whole pages.
    await scenario('PR-dominated repository', 'PPPPPPPIPPPPIPPP', 2)
    await scenario('all pull requests, no issues at all', 'PPPPPP', 3)

    # Boundaries.
    await scenario('pages land exactly on max_results', 'IIIIII', 3)
    await scenario('alternating issue and pull request', 'IPIPI', 2)
    await scenario('fewer records than max_results', 'II', 5)
    await scenario('empty repository', '', 3)
    await scenario('max_results=1 across mixed records', 'IPPIII', 1)

    # More pages than the internal bound, so one call cannot span them all.
    await scenario('more pages than MAX_LIST_PAGES',
                   'PPI' * (MAX_LIST_PAGES + 3), 4)

    print("\n2. Systematic sweep")

    parts = ['I', 'P', 'IP', 'PI', 'IIP', 'PPI', 'IIII', 'PPPP', 'IPIP']
    failures = []
    total = 0
    for a in parts:
        for b in parts:
            for max_results in (1, 2, 3, 5):
                total += 1
                records = a + b
                expected = issue_numbers(records)
                seen, error = await walk(records, max_results)
                if error:
                    failures.append(f"{records!r} max_results={max_results}: {error}")
                    continue
                missing = [n for n in expected if n not in seen]
                if missing:
                    failures.append(
                        f"{records!r} max_results={max_results}: missed {missing}")

    check(f'sweep of {total} record layouts loses nothing',
          not failures, '; '.join(failures[:4]))

    print("\n3. Invariants on a single response")

    out = await list_once('IIPPIIII', 3)
    check('max_results is filled when enough issues exist',
          len(out.issues) == 3, str([i.number for i in out.issues]))
    check('returned_count matches the payload',
          out.returned_count == len(out.issues), str(out.returned_count))
    check('list_issues sets no total_count',
          out.total_count is None, str(out.total_count))
    check('pull requests are filtered out by default',
          all(not i.is_pull_request for i in out.issues))

    out = await list_once('IIPPIIII', 3)
    check('a discarded page is re-offered rather than skipped',
          out.next_page is not None and out.next_page <= 2,
          f"next_page={out.next_page}")

    out = await list_once('II', 5)
    check('a complete single page reports no next_page',
          out.next_page is None and not out.truncated,
          f"next_page={out.next_page} truncated={out.truncated}")

    out = await list_once('IIPPIIII', 10)
    check('include_pull_requests=false never returns a PR',
          all(not i.is_pull_request for i in out.issues))

    client = FakeClient('PPI' * (MAX_LIST_PAGES + 3))
    tool = GitHubIssueTool({}, client)
    await tool._list_issues(GitHubIssueListInput(
        operation='list_issues', owner='o', repo='r', state='all', max_results=10))
    check(f'one call costs at most MAX_LIST_PAGES ({MAX_LIST_PAGES}) requests',
          len(client.requests) <= MAX_LIST_PAGES, f"made {len(client.requests)}")

    await test_every_list_operation()

    print("\n" + "=" * 62)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for failure in FAILED:
        print(f"  FAILED: {failure}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
