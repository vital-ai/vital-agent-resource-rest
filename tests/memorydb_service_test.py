#!/usr/bin/env python3
"""Tests for the shared MemoryDB service.

The service is global — configured once under {ENV}__MEMORYDB__* — and each tool
opts in separately. These tests cover that contract: an unconfigured service must
be inert rather than fatal, and a configured one must provide the primitives the
idempotency design rests on.

Runs against the real cluster when {ENV}__MEMORYDB__URL is set and reachable, and
skips the live section otherwise, so it is safe in CI without VPC access.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from vital_agent_resource_app.services import redis_client
from vital_agent_resource_app.utils.env_config import EnvConfigLoader

PASSED, FAILED = [], []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


async def test_optional():
    """Unconfigured must be inert: no client, no raise, no startup failure."""
    print("\n1. The service is optional")

    client = redis_client.init_redis({})
    check('no config yields no client', client is None and redis_client.get_redis() is None)
    check('ping on an unconfigured service is False, not an exception',
          await redis_client.ping() is False)
    await redis_client.close_redis()
    check('closing an unconfigured service is a no-op', True)

    client = redis_client.init_redis({'url': 'rediss://u:p@nonexistent.invalid:6379'})
    check('a configured-but-dead service still yields a client', client is not None)
    check('ping reports unreachable rather than raising',
          await redis_client.ping() is False,
          'a caller must be able to choose fail-open; an exception removes that choice')
    await redis_client.close_redis()


async def test_config_is_global():
    """Connection lives in the global section, never in a tool."""
    print("\n2. Configuration shape")

    cfg = EnvConfigLoader.load_config()['vital_agent_resource_app']
    check('load_config exposes a memorydb section', 'memorydb' in cfg, str(sorted(cfg)))

    github = next((t for t in cfg['tools'] if t['tool_id'] == 'github_tool'), {})
    leaked = [k for k in github if k.startswith('memorydb') or k == 'url']
    check('no tool carries connection details', not leaked,
          f"github_tool leaked {leaked} -- the connection belongs to the service")

    check('get_memorydb_config agrees with load_config',
          EnvConfigLoader.get_memorydb_config().get('url') == cfg['memorydb'].get('url'))


async def test_live():
    """Primitives the idempotency design depends on, against the real cluster."""
    print("\n3. Live cluster")

    cfg = EnvConfigLoader.get_memorydb_config()
    if not cfg.get('url'):
        print("  SKIP  no {ENV}__MEMORYDB__URL configured")
        return

    redis_client.init_redis(cfg)
    if not await redis_client.ping():
        print("  SKIP  cluster not reachable from here (VPC access required)")
        await redis_client.close_redis()
        return

    r = redis_client.get_redis()
    key = f"gh:idem:v1:selftest:{os.getpid()}"
    try:
        first = await r.set(key, "pending:a", nx=True, px=5000)
        second = await r.set(key, "pending:b", nx=True, px=5000)
        check('SET NX admits exactly one writer',
              first is True and second is None, f"first={first} second={second}")

        pttl = await r.pttl(key)
        check('PTTL yields the pending age without a stored timestamp',
              0 < pttl <= 5000, f"pttl={pttl}")

        check('the losing writer can read the winner value',
              await r.get(key) == "pending:a")

        await r.set(key, "issue:42", px=5000)
        check('the resolved value overwrites the reservation',
              await r.get(key) == "issue:42")

        # Concurrency is the property the whole design rests on.
        race_key = f"{key}:race"
        results = await asyncio.gather(*[
            r.set(race_key, f"w{i}", nx=True, px=5000) for i in range(20)
        ])
        winners = [x for x in results if x]
        check('exactly one of 20 concurrent claims wins',
              len(winners) == 1, f"{len(winners)} winners")
        await r.delete(race_key)
    finally:
        await r.delete(key)
        await redis_client.close_redis()


async def main():
    print("MemoryDB shared service tests")
    print("=" * 60)
    await test_optional()
    await test_config_is_global()
    await test_live()
    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
