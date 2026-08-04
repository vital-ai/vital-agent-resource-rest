"""
Shared Redis (MemoryDB) client singleton.

Ported from vital-chatwoot-bridge (services/redis_client.py), which talks to the
same MemoryDB cluster. Two things about that cluster drive this module:

  - It runs cluster_enabled=1, so RedisCluster is required. A plain Redis client
    connects and then fails on MOVED redirects, which looks like an intermittent
    bug rather than a configuration error.
  - MemoryDB is TLS-only, hence rediss:// and ssl=True.

Config differs from the bridge: this service reads {ENV}__TOOL__GITHUB__MEMORYDB_*
through EnvConfigLoader's per-tool prefix scan, so no shared config change is
needed to add it.

Usage:
    from vital_agent_resource_app.services.redis_client import get_redis

    r = get_redis()
    if r is not None:
        await r.ping()
"""

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import redis.asyncio as aioredis

logger = logging.getLogger("VitalAgentContainerLogger")

_client: Optional[aioredis.RedisCluster] = None


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def init_redis(config: Optional[Dict[str, Any]]) -> Optional[aioredis.RedisCluster]:
    """Build the global RedisCluster client from a tool config block.

    Returns None when no URL is configured, which is the normal state for a
    deployment that does not use idempotency. Does not connect -- redis-py
    connects lazily, so call ping() to find out whether the cluster is actually
    reachable.
    """
    global _client

    url = (config or {}).get('memorydb_url')
    if not url:
        logger.info("MemoryDB: no URL configured; idempotency features are unavailable")
        _client = None
        return None

    parsed = urlparse(url)
    _client = aioredis.RedisCluster(
        host=parsed.hostname,
        port=parsed.port or 6379,
        username=parsed.username or "default",
        password=parsed.password,
        ssl=_as_bool((config or {}).get('memorydb_ssl'), True),
        ssl_cert_reqs=(config or {}).get('memorydb_ssl_cert_reqs') or "none",
        decode_responses=True,
    )
    logger.info(
        f"MemoryDB: initialized RedisCluster host={parsed.hostname}:{parsed.port or 6379} "
        f"user={parsed.username or 'default'} ssl=True"
    )
    return _client


def get_redis() -> Optional[aioredis.RedisCluster]:
    """The global client, or None if MemoryDB is not configured."""
    return _client


async def ping() -> bool:
    """Whether the cluster answers. Never raises -- callers decide the policy."""
    if _client is None:
        return False
    try:
        await _client.ping()
        return True
    except Exception as e:
        logger.warning(f"MemoryDB: ping failed: {type(e).__name__}: {e}")
        return False


async def close_redis() -> None:
    """Close the global client."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception as e:  # pragma: no cover - shutdown best effort
            logger.warning(f"MemoryDB: error on close: {e}")
        logger.info("MemoryDB: connection closed")
        _client = None
