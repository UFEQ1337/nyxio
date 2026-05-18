"""Czysta logika odczytu snapshotu kolejki (do /wznow). Bez I/O."""

from __future__ import annotations

from typing import Any

from nyxio.core.queue import LoopMode


def restore_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Snapshot -> uporządkowana lista pozycji do ponownego dodania.

    Najpierw bieżący (zagra od początku), potem kolejka. Pomija wpisy bez uri.
    """
    entries: list[dict[str, Any]] = []
    current = snapshot.get("current")
    if current:
        entries.append(current)
    entries.extend(snapshot.get("upcoming") or [])
    return [e for e in entries if e and e.get("uri")]


def restore_loop(snapshot: dict[str, Any]) -> LoopMode:
    try:
        return LoopMode(snapshot.get("loop_mode", "none"))
    except ValueError:
        return LoopMode.NONE
