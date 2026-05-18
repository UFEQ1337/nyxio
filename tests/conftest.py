"""Wspólne fixture'y testowe."""

from __future__ import annotations

import pytest

from nyxio.core.track import Track


@pytest.fixture
def make_track():
    def _factory(title: str = "Test", length: int | None = 100_000) -> Track:
        return Track(
            title=title,
            uri=f"https://yt/{title}",
            length=length,
            artwork=None,
            author="tester",
            requested_by_id=1,
            requested_by_name="tester",
            playable=object(),  # placeholder; logika kolejki nie używa
        )

    return _factory
