"""Funkcje pomocnicze formatowania (czas, paginacja)."""

from __future__ import annotations

from collections.abc import Sequence


def format_duration(seconds: int | float | None) -> str:
    """Sekundy -> 'M:SS' lub 'H:MM:SS'. None/0 -> 'LIVE'."""
    if not seconds:
        return "LIVE"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def paginate[T](items: Sequence[T], page: int, per_page: int = 10) -> tuple[list[T], int]:
    """Zwraca (elementy_strony, liczba_stron). Strony liczone od 1."""
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    return list(items[start : start + per_page]), pages
