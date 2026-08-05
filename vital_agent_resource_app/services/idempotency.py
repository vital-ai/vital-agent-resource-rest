"""
Idempotency index backed by the shared MemoryDB service.

The primitive is `SET key value NX PX ttl`, which is atomic and therefore both
the check and the claim -- a read-then-write would race between replicas, which
is the entire failure this exists to prevent.

Two-phase, because the dangerous interval is between deciding to create and
knowing the issue number:

    pending:{request_id}   a reservation; the creator is mid-flight or died
    issue:{number}         resolved; this key maps to a known issue

Kept separate from the GitHub tool so it can be tested without GitHub, and so a
second consumer does not have to reimplement it.
"""

import hashlib
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger("VitalAgentContainerLogger")

KEY_PREFIX = "gh:idem:v1"

# Marker embedded in the issue body so GitHub can act as the durable fallback
# index when the reservation is lost. An HTML comment, so it does not render.
MARKER_TEMPLATE = "<!-- idempotency-key: {digest} -->"


def digest(idempotency_key: str) -> str:
    """Stable short digest of a caller's key.

    Hashed rather than used raw: callers pass Slack message ids, alert
    fingerprints and arbitrary text, so hashing bounds the length and keeps
    delimiters and newlines out of both the Redis key and the issue body.
    """
    return hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:32]


def build_key(owner: str, repo: str, idempotency_key: str) -> str:
    """Redis key for one (repo, caller key) pair.

    Repo-scoped because the same marker in two repositories is two legitimate
    issues; a global namespace would silently suppress the second.
    """
    return f"{KEY_PREFIX}:{owner}/{repo}:{digest(idempotency_key)}"


def build_marker(idempotency_key: str) -> str:
    return MARKER_TEMPLATE.format(digest=digest(idempotency_key))


class IdempotencyStore:
    """Reservation index over a Redis-compatible client."""

    def __init__(self, client: Any, pending_ttl: int, resolved_ttl: int):
        self._r = client
        self.pending_ttl = pending_ttl
        self.resolved_ttl = resolved_ttl

    async def reserve(self, key: str, request_id: str) -> bool:
        """Claim the key. True if this caller now owns the create."""
        result = await self._r.set(
            key, f"pending:{request_id}", nx=True, px=self.pending_ttl * 1000
        )
        return bool(result)

    async def resolve(self, key: str, issue_number: int) -> None:
        """Record the created issue. Overwrites the reservation deliberately."""
        await self._r.set(key, f"issue:{issue_number}", px=self.resolved_ttl * 1000)

    async def release(self, key: str) -> None:
        """Drop the reservation so a retry is not blocked until it expires.

        Only for *definite* failures. On an ambiguous one -- a timeout, where the
        issue may actually have been created -- the reservation must stay, so
        reconciliation resolves it against GitHub rather than a retry starting
        from a clean slate and filing a duplicate.
        """
        await self._r.delete(key)

    async def read(self, key: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """Current state of a key.

        Returns (state, issue_number, pending_age_seconds) where state is
        'issue', 'pending' or None.

        Pending age comes from PTTL rather than a timestamp in the value: no
        clock is involved, so it cannot be skewed between replicas.
        """
        value = await self._r.get(key)
        if not value:
            return None, None, None

        if value.startswith("issue:"):
            try:
                return 'issue', int(value.split(":", 1)[1]), None
            except (ValueError, IndexError):
                logger.warning(f"Idempotency key {key} holds an unparseable value {value!r}")
                return None, None, None

        if value.startswith("pending:"):
            remaining_ms = await self._r.pttl(key)
            age = None
            if isinstance(remaining_ms, int) and remaining_ms >= 0:
                age = max(0, self.pending_ttl - int(remaining_ms / 1000))
            return 'pending', None, age

        logger.warning(f"Idempotency key {key} holds an unrecognized value {value!r}")
        return None, None, None
