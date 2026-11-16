"""
Shared Redis (MemoryDB) client singleton.

Ported from vital-chatwoot-bridge (services/redis_client.py). The client type
follows the URL, because the deployed and local servers differ:

  - AWS MemoryDB (deployed): cluster_enabled=1 behind a clustercfg.* endpoint, so
    RedisCluster is required. A plain Redis client connects and then fails on
    MOVED redirects, which looks like an intermittent bug rather than a
    configuration error. MemoryDB is TLS-only: rediss://.
  - Local development: standalone Redis (cardiff-redis-streams on :6381), no TLS:
    redis://. RedisCluster refuses a server without cluster mode, so a standalone
    URL gets a plain Redis client.

A local run must never point at the deployed cluster: idempotency keys carry no
environment prefix, so a local run would read and write the deployed service's
reservations.

Configured as a **global service**, not per tool: {ENV}__MEMORYDB__* defines the
connection once, and any tool opts in separately with its own policy. A tool
config therefore never carries connection details -- adding a second consumer
means adding a flag to that tool, not another copy of the URL.

Usage:
    from vital_agent_resource_app.services.redis_client import get_redis

    r = get_redis()
    if r is not None:            # None means the service is not configured
        await r.ping()
"""

import logging
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

import redis.asyncio as aioredis

logger = logging.getLogger("VitalAgentContainerLogger")

RedisClient = Union[aioredis.Redis, aioredis.RedisCluster]

_client: Optional[RedisClient] = None


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def _is_cluster(config: Dict[str, Any], hostname: Optional[str]) -> bool:
    """Cluster mode unless told otherwise or the host is evidently standalone.

    An explicit {ENV}__MEMORYDB__CLUSTER wins. Otherwise a MemoryDB clustercfg.*
    endpoint is a cluster and anything else is standalone.
    """
    if config.get('cluster') is not None:
        return _as_bool(config.get('cluster'))
    return (hostname or '').startswith('clustercfg.')


def init_redis(config: Optional[Dict[str, Any]]) -> Optional[RedisClient]:
    """Build the global client from the shared memorydb config.

    Returns None when no URL is configured, which is the normal state for a
    deployment that does not use idempotency. Does not connect -- redis-py
    connects lazily, so call ping() to find out whether the server is actually
    reachable.
    """
    global _client

    config = config or {}
    url = config.get('url')
    if not url:
        logger.info("MemoryDB: no URL configured; idempotency features are unavailable")
        _client = None
        return None

    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port or 6379
    # TLS follows the scheme unless set explicitly: rediss:// is TLS, redis:// is not.
    ssl = _as_bool(config.get('ssl'), parsed.scheme == 'rediss')
    tls_kwargs = (
        {'ssl': True, 'ssl_cert_reqs': config.get('ssl_cert_reqs') or "none"}
        if ssl else {}
    )
    cluster = _is_cluster(config, host)

    if cluster:
        _client = aioredis.RedisCluster(
            host=host,
            port=port,
            username=parsed.username or "default",
            password=parsed.password,
            decode_responses=True,
            **tls_kwargs,
        )
    else:
        db = int((parsed.path or '/0').lstrip('/') or 0)
        _client = aioredis.Redis(
            host=host,
            port=port,
            db=db,
            username=parsed.username,
            password=parsed.password,
            decode_responses=True,
            **tls_kwargs,
        )
    logger.info(
        f"MemoryDB: initialized {'RedisCluster' if cluster else 'standalone Redis'} "
        f"host={host}:{port} user={parsed.username or 'default'} ssl={ssl}"
    )
    return _client


def get_redis() -> Optional[RedisClient]:
    """The global client, or None if MemoryDB is not configured."""
    return _client


async def ping() -> bool:
    """Whether the server answers. Never raises -- callers decide the policy."""
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
