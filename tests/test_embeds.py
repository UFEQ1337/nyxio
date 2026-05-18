"""Testy buderów embedów (pomoc, formatowanie czasu kolejki)."""

from __future__ import annotations

from nyxio.ui.embeds import _total, help_embed


def test_total_empty_queue_is_dash():
    assert _total(0) == "—"
    assert _total(-5) == "—"


def test_total_formats_minutes():
    assert _total(180_000) == "3:00"


def test_help_embed_lists_categories():
    e = help_embed()
    names = [f.name for f in e.fields]
    assert any("Odtwarzanie" in n for n in names)
    assert any("Kolejka" in n for n in names)
    assert any("Dźwięk" in n for n in names)
    joined = " ".join(f.value for f in e.fields)
    assert "/play" in joined and "/pomoc" not in joined  # /pomoc się nie listuje
