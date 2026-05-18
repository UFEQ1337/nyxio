"""Wyjątki domenowe Nyxio."""

from __future__ import annotations


class NyxioError(Exception):
    """Bazowy wyjątek domenowy."""


class NotInVoiceError(NyxioError):
    """Użytkownik nie znajduje się na kanale głosowym."""


class QueueFullError(NyxioError):
    """Kolejka osiągnęła limit pojemności."""
