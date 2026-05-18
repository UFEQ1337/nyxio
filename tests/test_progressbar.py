"""Testy paska postępu (czyste)."""

from __future__ import annotations

from nyxio.utils.progressbar import render_progress


def test_live_when_no_length():
    assert render_progress(0, None) == "● NA ŻYWO"
    assert render_progress(1000, 0) == "● NA ŻYWO"


def test_start_position():
    out = render_progress(0, 240_000, width=10)
    assert out.startswith("0:00 ")
    assert out.endswith(" 4:00")
    assert "🔘" in out


def test_knob_moves_with_position():
    start = render_progress(0, 200_000, width=20)
    mid = render_progress(100_000, 200_000, width=20)
    end = render_progress(199_000, 200_000, width=20)
    assert start.index("🔘") < mid.index("🔘") < end.index("🔘")


def test_position_clamped_over_length():
    out = render_progress(999_999, 100_000, width=10)
    assert "🔘" in out  # nie wychodzi poza pasek
    assert out.endswith(" 1:40")


def test_bar_width_constant():
    out = render_progress(50_000, 100_000, width=15)
    bar = out.split(" ")[1]
    assert len(bar) == 15  # filled + knob + empty
