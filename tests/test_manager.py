"""PlayerManager.teardown — kontrola czyszczenia snapshotu (Fix 3).

Snapshot w state_store ma przetrwać graceful restart (shutdown_all),
ale świadome /stop oraz idle-timeout mają go czyścić.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nyxio.core.manager import PlayerManager


@pytest.fixture
def manager():
    settings = MagicMock()
    settings.redis_url = None
    m = PlayerManager(settings, MagicMock())
    m.state_store = MagicMock()
    m.state_store.clear_queue = AsyncMock()
    m.state_store.close = AsyncMock()
    return m


def _add_fake_player(manager: PlayerManager, guild_id: int) -> MagicMock:
    fake = MagicMock()
    fake.shutdown = AsyncMock()
    manager._players[guild_id] = fake
    return fake


async def test_teardown_clears_state_by_default(manager):
    fake = _add_fake_player(manager, 42)
    await manager.teardown(42)
    fake.shutdown.assert_awaited_once()
    manager.state_store.clear_queue.assert_awaited_once_with(42)


async def test_teardown_can_keep_state(manager):
    _add_fake_player(manager, 42)
    await manager.teardown(42, clear_state=False)
    manager.state_store.clear_queue.assert_not_awaited()


async def test_shutdown_all_preserves_snapshot(manager):
    _add_fake_player(manager, 1)
    _add_fake_player(manager, 2)
    await manager.shutdown_all()
    manager.state_store.clear_queue.assert_not_awaited()
    manager.state_store.close.assert_awaited_once()
    assert manager._players == {}
