"""Nadzór nad taskami per-gildia: izolacja błędów, strukturalne logowanie."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from nyxio.infra.logging import get_logger

log = get_logger("supervisor")


def supervise(
    coro_factory: Callable[[], Awaitable[None]],
    *,
    guild_id: int,
    name: str,
) -> asyncio.Task[None]:
    """Owija coroutine w task z izolacją wyjątków.

    Wyjątek w pętli jednej gildii jest logowany, ale nie propaguje
    i nie ubija pętli pozostałych gildii.
    """

    async def _runner() -> None:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — celowo szeroki: izolacja per-gildia
            log.exception("task_crashed", guild_id=guild_id, task=name)

    return asyncio.create_task(_runner(), name=f"{name}:{guild_id}")
