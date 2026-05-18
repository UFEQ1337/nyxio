"""Testy GuildPlayer na silniku Lavalink/wavelink (mock wavelink.Player)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nyxio.core.player import GuildPlayer, PlayerState


@pytest.fixture
async def player():
    wl = MagicMock()  # wavelink.Player
    wl.playing = False
    wl.paused = False
    wl.play = AsyncMock()
    wl.stop = AsyncMock()
    wl.pause = AsyncMock()
    wl.seek = AsyncMock()
    wl.set_volume = AsyncMock()
    wl.set_filters = AsyncMock()
    wl.disconnect = AsyncMock()

    manager = MagicMock()
    manager.settings.max_queue_size = 100
    manager.settings.idle_timeout_seconds = 999  # nie odpalaj idle w testach
    manager.state_store.save_queue = AsyncMock()
    manager.teardown = AsyncMock()
    manager.guild_config.get_default_volume.return_value = 100
    manager.guild_config.set_default_volume = AsyncMock()
    manager.guild_config.get_autoplay.return_value = False
    manager.guild_config.set_autoplay = AsyncMock()

    p = GuildPlayer(42, wl, MagicMock(), manager)
    p._publish_now_playing = AsyncMock()  # UI poza zakresem tych testów
    yield p
    p._cancel_idle_timeout()


async def test_initial_state_idle(player):
    assert player.state is PlayerState.IDLE


async def test_enqueue_when_idle_starts_playback(player, make_track):
    await player.enqueue(make_track("a"))
    player.player.play.assert_awaited_once()
    assert player.state is PlayerState.PLAYING
    assert player.queue.current.title == "a"


async def test_enqueue_while_playing_does_not_restart(player, make_track):
    player.player.playing = True
    await player.enqueue(make_track("a"))
    player.player.play.assert_not_awaited()
    assert len(player.queue) == 1


async def test_pause_toggles_state(player):
    player.player.playing = True
    player.player.paused = False
    assert await player.pause() is True
    assert player.state is PlayerState.PAUSED
    player.player.pause.assert_awaited_with(True)

    player.player.playing = True
    player.player.paused = True
    assert await player.pause() is False
    assert player.state is PlayerState.PLAYING


async def test_skip_calls_wavelink_stop(player):
    player.player.playing = True
    await player.skip()
    player.player.stop.assert_awaited_once()


async def test_handle_track_end_advances(player, make_track):
    player.queue.add(make_track("a"))
    await player.handle_track_end("finished")
    player.player.play.assert_awaited_once()


async def test_handle_track_end_replaced_is_ignored(player, make_track):
    player.queue.add(make_track("a"))
    await player.handle_track_end("TrackEndReason.replaced")
    player.player.play.assert_not_awaited()


async def test_default_volume_from_config(player):
    assert player.volume_pct == 100


async def test_set_volume_clamps_and_persists(player):
    assert await player.set_volume(250) == 200
    player.player.set_volume.assert_awaited_with(200)
    assert await player.set_volume(-30) == 0
    player._manager.guild_config.set_default_volume.assert_awaited_with(42, 0)


async def test_seek_clamps_negative(player):
    await player.seek(-5000)
    player.player.seek.assert_awaited_with(0)


async def test_set_filter_invokes_player(player):
    await player.set_filter("nightcore")
    player.player.set_filters.assert_awaited_once()


async def test_previous_no_history_returns_false(player, make_track):
    player.queue.add(make_track("a"))
    player.queue.get_next()  # brak historii
    assert await player.previous() is False


async def test_previous_with_history_stops_playback(player, make_track):
    a, b = make_track("a"), make_track("b")
    player.queue.add(a)
    player.queue.add(b)
    player.queue.get_next()  # a
    player.queue.get_next()  # b, a -> historia
    player.player.playing = True
    assert await player.previous() is True
    player.player.stop.assert_awaited_once()


async def test_position_ms_zero_when_idle(player):
    player.player.playing = False
    player.player.paused = False
    assert player.position_ms == 0


async def test_position_ms_reports_wavelink_position(player):
    player.player.playing = True
    player.player.position = 42_000
    assert player.position_ms == 42_000


async def test_toggle_autoplay_persists(player):
    assert player.autoplay is False
    assert await player.toggle_autoplay() is True
    assert player.autoplay is True
    player._manager.guild_config.set_autoplay.assert_awaited_with(42, True)


async def test_autoplay_queues_related_when_empty(player, make_track, monkeypatch):
    import nyxio.core.player as player_mod

    last = make_track("last")
    last.playable = MagicMock(identifier="vid1")
    player._last_track = last
    player.autoplay = True

    rec = MagicMock(identifier="vid2")
    rec.title = "Powiązany"
    search = AsyncMock(return_value=[rec])
    monkeypatch.setattr(player_mod.wavelink.Playable, "search", search)

    await player._advance()  # kolejka pusta -> autoplay dokłada -> gra
    search.assert_awaited_once()
    player.player.play.assert_awaited_once()


async def test_no_autoplay_when_disabled(player):
    player.autoplay = False
    await player._advance()  # pusto, autoplay off -> idle
    player.player.play.assert_not_awaited()
    assert player.state is PlayerState.IDLE


async def test_previous_when_idle_advances(player, make_track):
    a, b = make_track("a"), make_track("b")
    player.queue.add(a)
    player.queue.add(b)
    player.queue.get_next()
    player.queue.get_next()
    player.player.playing = False
    player.player.paused = False
    assert await player.previous() is True
    player.player.play.assert_awaited()


# ---- Fix 2: pętla zamiast rekurencji + komunikat o błędzie ---------------


async def test_play_failures_stop_after_limit_and_notify(player, make_track):
    """Seria nieudanych play kończy się IDLE + 1 komunikat (bez RecursionError)."""
    import nyxio.core.player as player_mod

    for name in ("a", "b", "c", "d", "e"):
        player.queue.add(make_track(name))
    player.player.play = AsyncMock(side_effect=RuntimeError("boom"))
    player.text_channel.send = AsyncMock()

    await player._advance()

    assert player.player.play.await_count == player_mod._MAX_PLAY_FAILURES
    assert player.state is PlayerState.IDLE
    player.text_channel.send.assert_awaited_once()


async def test_advance_skips_failing_track_then_plays_next(player, make_track):
    player.queue.add(make_track("bad"))
    player.queue.add(make_track("good"))
    player.player.play = AsyncMock(side_effect=[RuntimeError("boom"), None])

    await player._advance()

    assert player.player.play.await_count == 2
    assert player.state is PlayerState.PLAYING
    assert player._last_track.title == "good"


# ---- Fix 1: lock serializujący _advance (regresja: brak deadlocku) -------


async def test_concurrent_advance_consumes_each_track_once(player, make_track):
    import asyncio

    player.queue.add(make_track("a"))
    player.queue.add(make_track("b"))

    await asyncio.gather(player._advance(), player._advance())

    assert player.player.play.await_count == 2
    assert len(player.queue) == 0


# ---- Fix 3: persist po mutacjach kolejki --------------------------------


async def test_skip_persists_snapshot(player):
    import asyncio

    player.player.playing = True
    await player.skip()
    await asyncio.sleep(0)  # pozwól dobiec fire-and-forget snapshotowi
    player._manager.state_store.save_queue.assert_awaited()


async def test_shuffle_and_loop_persist(player, make_track):
    import asyncio

    player.queue.add(make_track("a"))
    player.shuffle()
    player.cycle_loop()
    await asyncio.sleep(0)
    assert player._manager.state_store.save_queue.await_count >= 1
