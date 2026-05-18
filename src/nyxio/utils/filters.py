"""Presety filtrów audio Lavalink (mapowanie czyste + aplikacja na wavelink).

Specyfikacje presetów to zwykłe dane (testowalne bez wavelink);
`apply_filter_preset` przekłada je na obiekt wavelink.Filters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import wavelink

# preset -> specyfikacja (puste = reset do czystego dźwięku)
FILTER_PRESETS: dict[str, dict[str, Any]] = {
    "none": {},
    "bass": {
        "equalizer": [
            {"band": 0, "gain": 0.25},
            {"band": 1, "gain": 0.25},
            {"band": 2, "gain": 0.15},
        ]
    },
    "nightcore": {"timescale": {"speed": 1.2, "pitch": 1.2, "rate": 1.0}},
    "eq": {"equalizer": [{"band": b, "gain": 0.2} for b in range(5)]},
}

PRESET_NAMES = tuple(FILTER_PRESETS)


async def apply_filter_preset(player: wavelink.Player, preset: str) -> None:
    """Buduje świeże wavelink.Filters wg presetu i ustawia je na playerze."""
    import wavelink

    spec = FILTER_PRESETS[preset]
    filters: wavelink.Filters = wavelink.Filters()  # pusty = reset
    if "timescale" in spec:
        filters.timescale.set(**spec["timescale"])
    if "equalizer" in spec:
        filters.equalizer.set(bands=spec["equalizer"])
    await player.set_filters(filters)
