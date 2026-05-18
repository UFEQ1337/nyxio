"""Testy presetów filtrów (czysta mapa) i aplikacji na player."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from nyxio.utils.filters import FILTER_PRESETS, PRESET_NAMES, apply_filter_preset


def test_preset_names_cover_required():
    assert set(PRESET_NAMES) >= {"none", "bass", "nightcore", "eq"}


def test_none_preset_is_empty():
    assert FILTER_PRESETS["none"] == {}


def test_nightcore_speeds_up():
    ts = FILTER_PRESETS["nightcore"]["timescale"]
    assert ts["speed"] > 1.0 and ts["pitch"] > 1.0


def test_bass_boosts_low_bands():
    bands = FILTER_PRESETS["bass"]["equalizer"]
    assert all(b["gain"] > 0 for b in bands)
    assert {b["band"] for b in bands} <= set(range(15))


async def test_apply_filter_preset_sets_on_player():
    player = MagicMock()
    player.set_filters = AsyncMock()
    await apply_filter_preset(player, "nightcore")
    player.set_filters.assert_awaited_once()
