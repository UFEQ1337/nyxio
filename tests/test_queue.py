"""Testy logiki kolejki: kolejność, tryby loop, shuffle, limity."""

from __future__ import annotations

import pytest

from nyxio.core.queue import LoopMode, TrackQueue
from nyxio.utils.errors import QueueFullError


def test_total_length_ms(make_track):
    q = TrackQueue()
    q.add(make_track("a", length=120_000))
    q.add(make_track("b", length=None))  # bez długości — pomijane
    q.add(make_track("c", length=60_000))
    assert q.total_length_ms == 180_000


def test_fifo_order(make_track):
    q = TrackQueue()
    a, b = make_track("a"), make_track("b")
    q.add(a)
    q.add(b)
    assert q.get_next() is a
    assert q.get_next() is b
    assert q.get_next() is None


def test_loop_track_repeats_current(make_track):
    q = TrackQueue()
    a = make_track("a")
    q.add(a)
    assert q.get_next() is a
    q.loop_mode = LoopMode.TRACK
    assert q.get_next() is a
    assert q.get_next() is a


def test_loop_queue_recycles(make_track):
    q = TrackQueue()
    a, b = make_track("a"), make_track("b")
    q.add(a)
    q.add(b)
    q.loop_mode = LoopMode.QUEUE
    assert q.get_next() is a
    assert q.get_next() is b
    assert q.get_next() is a  # a wrócił na koniec


def test_cycle_loop_order():
    q = TrackQueue()
    assert q.cycle_loop() is LoopMode.TRACK
    assert q.cycle_loop() is LoopMode.QUEUE
    assert q.cycle_loop() is LoopMode.NONE


def test_max_size_enforced(make_track):
    q = TrackQueue(max_size=1)
    q.add(make_track("a"))
    with pytest.raises(QueueFullError):
        q.add(make_track("b"))


def test_clear_resets_state(make_track):
    q = TrackQueue()
    q.add(make_track("a"))
    q.get_next()
    q.loop_mode = LoopMode.QUEUE
    q.clear()
    assert len(q) == 0
    assert q.current is None
    assert q.loop_mode is LoopMode.NONE


def test_previous_returns_to_played_track(make_track):
    q = TrackQueue()
    a, b, c = make_track("a"), make_track("b"), make_track("c")
    for t in (a, b, c):
        q.add(t)
    assert q.get_next() is a
    assert q.get_next() is b  # a -> historia
    assert q.has_previous is True
    assert q.previous() is True
    # następny powinien być poprzednio grany 'a', potem wraca 'b'
    assert q.get_next() is a
    assert q.get_next() is b
    assert q.get_next() is c


def test_previous_without_history(make_track):
    q = TrackQueue()
    q.add(make_track("a"))
    q.get_next()  # 'a' bieżący, historia pusta
    assert q.has_previous is False
    assert q.previous() is False


def test_previous_then_forward_chain(make_track):
    q = TrackQueue()
    a, b = make_track("a"), make_track("b")
    q.add(a)
    q.add(b)
    q.get_next()            # a
    q.get_next()            # b (a w historii)
    assert q.previous()     # cofnij
    assert q.get_next() is a
    # 'b' przekolejkowane na przód — gra po 'a'
    assert q.get_next() is b


def test_clear_wipes_history(make_track):
    q = TrackQueue()
    q.add(make_track("a"))
    q.add(make_track("b"))
    q.get_next()
    q.get_next()
    assert q.has_previous
    q.clear()
    assert q.has_previous is False
    assert q.previous() is False
