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
from vital_agent_resource_app.tools.github.issue_models import GitHubIssueListInput

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

    async def async_list_for_repo(self, *args, **kwargs):  # pragma: no cover - unused
        raise AssertionError("call() should intercept before reaching the endpoint")

    def check_repo(self, owner, repo):
        return f"{owner}/{repo}"

    def check_write_allowed(self, *args, **kwargs):
        return None

    async def call(self, func, *args, context='', **kwargs):
        page = kwargs.get('page', 1)
        per_page = kwargs.get('per_page', 30)
        self.requests.append(page)

        start = (page - 1) * per_page
        window = self.records[start:start + per_page]

        payload = []
        for offset, kind in enumerate(window):
            number = start + offset + 1   # stable id: position in the record list
            item = {
                'number': number,
                'title': f"record {number}",
                'state': 'open',
                'html_url': f"https://example.invalid/{number}",
                'user': {'login': 'tester'},
                'labels': [],
                'assignees': [],
                'comments': 0,
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


async def main():
    print("Synthetic pagination tests for list_issues")
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

    print("\n" + "=" * 62)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for failure in FAILED:
        print(f"  FAILED: {failure}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
