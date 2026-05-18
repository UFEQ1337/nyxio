"""Pasek postępu odtwarzania (czysta logika, testowalna).

Discord nie ma natywnego suwaka — renderujemy go znakami.
Wartości pochodzą z wavelink (player.position / track.length).
"""

from __future__ import annotations

_FILLED = "━"
_KNOB = "🔘"
_EMPTY = "─"


def _fmt(ms: int) -> str:
    """ms -> 'M:SS' / 'H:MM:SS' (0 -> '0:00', nie 'LIVE')."""
    total = max(0, ms) // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def render_progress(position_ms: int, length_ms: int | None, width: int = 18) -> str:
    """'1:23 ━━━━━🔘──────── 4:53'. length 0/None -> znacznik NA ŻYWO."""
    if not length_ms or length_ms <= 0:
        return "● NA ŻYWO"
    pos = max(0, min(position_ms, length_ms))
    ratio = pos / length_ms
    knob = min(width - 1, int(ratio * width))
    bar = _FILLED * knob + _KNOB + _EMPTY * (width - knob - 1)
    return f"{_fmt(pos)} {bar} {_fmt(length_ms)}"
