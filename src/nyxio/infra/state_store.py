"""Opcjonalny write-through snapshot stanu kolejek do Redis.

Źródłem prawdy pozostaje pamięć procesu — Redis to warstwa persystencji
służąca diagnostyce i opcjonalnemu odtworzeniu kolejki po restarcie.
Gdy redis_url nie jest skonfigurowany, store działa jako no-op.
"""

from __future__ import annotations

import json
from typing import Any, cast

from nyxio.infra.logging import get_logger

log = get_logger("state_store")


class StateStore:
    def __init__(self, redis_url: str | None) -> None:
        self._url = redis_url
        self._client: Any | None = None

    async def connect(self) -> None:
        if not self._url:
            return
        try:
            import redis.asyncio as redis

            self._client = cast(Any, redis.from_url(self._url, decode_responses=True))
            await self._client.ping()
            log.info("redis_connected")
        except Exception:  # noqa: BLE001
            log.exception("redis_connect_failed")
            self._client = None

    async def save_queue(self, guild_id: int, snapshot: dict[str, Any]) -> None:
        if self._client is None:
            return
        try:
            await self._client.set(f"nyxio:queue:{guild_id}", json.dumps(snapshot))
        except Exception:  # noqa: BLE001
            log.exception("redis_save_failed", guild_id=guild_id)

    async def get_queue(self, guild_id: int) -> dict[str, Any] | None:
        """Odczytuje zapisany snapshot kolejki (do /wznow). None = brak."""
        if self._client is None:
            return None
        try:
            raw = await self._client.get(f"nyxio:queue:{guild_id}")
        except Exception:  # noqa: BLE001
            log.exception("redis_get_failed", guild_id=guild_id)
            return None
        if not raw:
            return None
        try:
            return cast(dict[str, Any], json.loads(raw))
        except json.JSONDecodeError:
            return None

    async def clear_queue(self, guild_id: int) -> None:
        if self._client is None:
            return
        try:
            await self._client.delete(f"nyxio:queue:{guild_id}")
        except Exception:  # noqa: BLE001
            log.exception("redis_clear_failed", guild_id=guild_id)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
