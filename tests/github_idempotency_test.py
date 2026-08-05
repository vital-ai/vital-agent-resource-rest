#!/usr/bin/env python3
"""Offline tests for idempotent create_issue.

No GitHub, no MemoryDB: a stub Redis and a stub GitHub client, so every branch of
the algorithm is reachable including the ones a live test cannot force -- a lost
reservation, an ambiguous timeout, a scan that runs out of budget.
"""

import asyncio
import os
import sys
import time

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

    async def set(self, key, value, nx=False, px=None, ex=None, xx=False, get=False):
        prior = self.data.get(key, (None, None))[0]
        if nx and key in self.data:
            return None
        if xx and key not in self.data:
            return prior if get else None
        self.data[key] = (value, px or (ex * 1000 if ex else None))
        return prior if get else True

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


async def test_live_race():
    """The abandoned-reservation race, against the real cluster.

    The stub above serialises, so a contender always reads a resolved key and
    never reaches the take-over -- which means the offline suite cannot prove
    this fix. Only true concurrency can. Verified by reverting the take-over:
    4 concurrent requests filed 4 duplicate issues.

    Skips without cluster access, so it is CI-safe.
    """
    print("\n6. Abandoned-reservation race (live)")

    import os as _os
    from dotenv import load_dotenv
    load_dotenv()
    from vital_agent_resource_app.utils.env_config import EnvConfigLoader
    from vital_agent_resource_app.services.idempotency import build_key as _bk
    from vital_agent_resource_app.tools.github.github_client import GitHubClient
    from vital_agent_resource_app.tools.github.issue_models import GitHubIssueCloseInput

    owner, repo = _os.getenv('GITHUB_TEST_OWNER'), _os.getenv('GITHUB_TEST_REPO')
    mem = EnvConfigLoader.get_memorydb_config()
    if not mem.get('url') or not owner:
        print("  SKIP  needs MemoryDB and GITHUB_TEST_OWNER/REPO")
        return

    redis_client.init_redis(mem)
    if not await redis_client.ping():
        print("  SKIP  cluster not reachable from here")
        await redis_client.close_redis()
        return

    cfg = dict(EnvConfigLoader.get_tool_config('github_tool'))
    cfg['idempotency_pending_grace'] = '1'
    tools = [GitHubIssueTool(cfg, GitHubClient(cfg)) for _ in range(4)]

    ikey = f"race-{int(time.time())}"
    rkey = _bk(owner, repo, ikey)
    r = redis_client.get_redis()
    await r.set(rkey, "pending:dead-request", px=3000)
    await asyncio.sleep(2.2)          # age it past the grace window

    def mk():
        return GitHubIssueCreateInput(
            operation='create_issue', owner=owner, repo=repo,
            title='[race] abandoned-reservation take-over', idempotency_key=ikey)

    outs = await asyncio.gather(*[t._create_issue(mk()) for t in tools],
                                return_exceptions=True)
    numbers = sorted({o.issue.number for o in outs if getattr(o, 'issue', None)})
    check('four concurrent take-overs file exactly one issue',
          len(numbers) == 1, f"filed {numbers}")
    check('exactly one reports created=true',
          sum(1 for o in outs if getattr(o, 'created', None) is True) == 1,
          str([getattr(o, 'created', None) for o in outs]))

    for n in numbers:
        await tools[0]._close_issue(GitHubIssueCloseInput(
            operation='close_issue', owner=owner, repo=repo,
            issue_number=n, state_reason='not_planned'))
    await r.delete(rkey)
    await redis_client.close_redis()


async def main():
    print("Idempotent create_issue")
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

    print("\n4b. Take-over of an abandoned reservation is atomic")
    # Two requests both find the same stale reservation, both scan, both find
    # nothing. Without an atomic take-over both create: two issues, one key.
    # Timeouts route into this path and a timeout usually means a retry is
    # already in flight, so this is the expected shape, not an unlucky one.
    r = StubRedis(); redis_client._client = r
    tool_a, gh_a = make_tool(existing=[])
    tool_b, gh_b = make_tool(existing=[])
    key = build_key('o', 'r', 'evt-race')
    await r.set(key, 'pending:dead', px=60000)
    r.pttl_override[key] = 1000
    outs = await asyncio.gather(
        tool_a._create_issue(create_input('evt-race')),
        tool_b._create_issue(create_input('evt-race')),
    )
    total_creates = len(gh_a.creates) + len(gh_b.creates)
    check('exactly one contender creates', total_creates == 1,
          f"{total_creates} issues filed for one key")
    losers = [o for o in outs if o.created is False]
    check('the other contender is told it did not create',
          len(losers) == 1, str([(o.created, o.api_error) for o in outs]))
    winner = next(o for o in outs if o.created is True)
    check('and is pointed at the same issue, or told it lost the take-over',
          (losers[0].issue and losers[0].issue.number == winner.issue.number)
          or 'took over' in (losers[0].api_error or ''),
          f"loser issue={losers[0].issue} error={losers[0].api_error}")

    # The two contenders above serialise through the stub, so the loser reads a
    # resolved key. Exercise the contended take-over directly, which is the case
    # that has to hold when they truly overlap.
    r2 = StubRedis()
    from vital_agent_resource_app.services.idempotency import IdempotencyStore
    store2 = IdempotencyStore(r2, pending_ttl=60, resolved_ttl=100)
    k2 = 'gh:idem:v1:o/r:contended'
    await r2.set(k2, 'pending:dead', px=60000)
    _, _, _, observed = await store2.read(k2)
    wins = [await store2.take_over(k2, observed, f'req{i}') for i in range(4)]
    check('exactly one of four take-overs wins', sum(1 for w in wins if w) == 1,
          f"{sum(1 for w in wins if w)} winners: {wins}")

    # The key expiring between the read and the take-over must not double-create.
    r = StubRedis(); redis_client._client = r
    tool, gh = make_tool(existing=[])
    key = build_key('o', 'r', 'evt-vanish')
    await r.set(key, 'pending:dead', px=60000)
    r.pttl_override[key] = 1000
    original_read = tool._idempotency_store
    async def vanish_then_create(vi):
        return await tool._create_issue(vi)
    # simulate: the key disappears just before take_over runs
    store = tool._idempotency_store()
    state, num, age, raw = await store.read(key)
    await r.delete(key)
    won = await store.take_over(key, raw, 'me')
    check('a vanished key falls back to a fresh reservation', won is True, str(won))
    check('and the reservation is now held', (await r.get(key)) == 'pending:me',
          str(await r.get(key)))

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

    await test_live_race()

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
