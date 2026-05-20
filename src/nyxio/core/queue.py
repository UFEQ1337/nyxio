"""Kolejka utworów: tryby loop, shuffle, limity. Czysta logika (bez I/O)."""

from __future__ import annotations

import enum
import random
from collections import deque

from nyxio.core.track import Track
from nyxio.utils.errors import QueueFullError


class LoopMode(enum.Enum):
    NONE = "none"
    TRACK = "track"
    QUEUE = "queue"


class TrackQueue:
    def __init__(self, max_size: int = 500) -> None:
        self._items: deque[Track] = deque()
        self._max_size = max_size
        self.loop_mode = LoopMode.NONE
        self._current: Track | None = None
        # Historia odtworzonych utworów (dla "poprzedni"). Ograniczona.
        self._history: deque[Track] = deque(maxlen=100)

    def __len__(self) -> int:
        return len(self._items)

    @property
    def current(self) -> Track | None:
        return self._current

    @property
    def upcoming(self) -> list[Track]:
        return list(self._items)

    @property
    def total_length_ms(self) -> int:
        """Łączny czas utworów w kolejce (ms); pomija pozycje bez długości."""
        return sum(t.length for t in self._items if t.length)

    def add(self, track: Track) -> None:
        if len(self._items) >= self._max_size:
            raise QueueFullError(f"Kolejka pełna (limit {self._max_size}).")
        self._items.append(track)

    def get_next(self) -> Track | None:
        """Zwraca następny utwór respektując tryb loop. None = pusto."""
        if self.loop_mode is LoopMode.TRACK and self._current is not None:
            return self._current
        if self.loop_mode is LoopMode.QUEUE and self._current is not None:
            self._items.append(self._current)
        elif self._current is not None:
            # Normalny przeskok do przodu — odtworzony trafia do historii.
            self._history.append(self._current)
        if not self._items:
            self._current = None
            return None
        self._current = self._items.popleft()
        return self._current

    @property
    def has_previous(self) -> bool:
        return bool(self._history)

    def previous(self) -> bool:
        """Cofa do poprzedniego utworu: poprzedni gra następny, a bieżący
        wraca na początek kolejki (by można było wrócić do przodu).
        Zwraca False, gdy brak historii."""
        if not self._history:
            return False
        prev = self._history.pop()
        if self._current is not None:
            self._items.appendleft(self._current)
        self._items.appendleft(prev)
        # Wyzeruj bieżący, by get_next nie wrzucił go ponownie do historii
        # (już go przekolejkowaliśmy).
        self._current = None
        return True

    def cycle_loop(self) -> LoopMode:
        order = [LoopMode.NONE, LoopMode.TRACK, LoopMode.QUEUE]
        self.loop_mode = order[(order.index(self.loop_mode) + 1) % len(order)]
        return self.loop_mode

    def shuffle(self) -> None:
        items = list(self._items)
        random.shuffle(items)
        self._items = deque(items)

    def clear(self) -> None:
        self._items.clear()
        self._history.clear()
        self._current = None
        self.loop_mode = LoopMode.NONE

    def to_snapshot(self) -> dict[str, object]:
        # Historia trafia do snapshotu, zeby graceful restart jej nie tracil
        # (na wypadek przyszlej rozbudowy /wznow o re-resolve historii).
        # Shuffle nie persystujemy — to per-sesja, swiadoma decyzja.
        return {
            "loop_mode": self.loop_mode.value,
            "current": self._current.to_snapshot() if self._current else None,
            "upcoming": [t.to_snapshot() for t in self._items],
            "history": [t.to_snapshot() for t in self._history],
        }
