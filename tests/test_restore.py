"""Testy czystej logiki odczytu snapshotu (restore)."""

from __future__ import annotations

from nyxio.core.queue import LoopMode
from nyxio.core.restore import restore_entries, restore_loop


def test_entries_current_first_then_upcoming():
    snap = {
        "current": {"uri": "u-cur", "title": "C"},
        "upcoming": [{"uri": "u1"}, {"uri": "u2"}],
    }
    out = restore_entries(snap)
    assert [e["uri"] for e in out] == ["u-cur", "u1", "u2"]


def test_entries_skip_without_uri_and_none_current():
    snap = {"current": None, "upcoming": [{"uri": "u1"}, {"title": "brak uri"}, {}]}
    assert [e["uri"] for e in restore_entries(snap)] == ["u1"]


def test_entries_empty_snapshot():
    assert restore_entries({}) == []


def test_restore_loop_valid_and_invalid():
    assert restore_loop({"loop_mode": "queue"}) is LoopMode.QUEUE
    assert restore_loop({"loop_mode": "track"}) is LoopMode.TRACK
    assert restore_loop({"loop_mode": "bzdura"}) is LoopMode.NONE
    assert restore_loop({}) is LoopMode.NONE
