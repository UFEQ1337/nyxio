"""Model utworu dla kolejki/UI. Budowany z wavelink.Playable.

Pole `playable` trzyma obiekt wavelink używany do odtwarzania; w testach
czystej logiki kolejki pozostaje None (Track jest wtedy konstruowany wprost).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import wavelink


@dataclass(slots=True)
class Track:
    title: str
    uri: str
    length: int | None  # długość w ms (0/None = stream/LIVE)
    artwork: str | None
    author: str | None
    requested_by_id: int
    requested_by_name: str
    playable: Any = None  # wavelink.Playable

    @classmethod
    def from_playable(
        cls,
        playable: wavelink.Playable,
        requester_id: int,
        requester_name: str,
    ) -> Track:
        uri = playable.uri or ""
        artwork = getattr(playable, "artwork", None)
        # Lavalink youtube-plugin często zwraca artworkUrl=None — składamy
        # przewidywalny URL miniatury YouTube z ID filmu.
        if not artwork:
            vid = getattr(playable, "identifier", None)
            if vid and ("youtube.com" in uri or "youtu.be" in uri):
                artwork = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        return cls(
            title=playable.title or "Nieznany utwór",
            uri=uri,
            length=getattr(playable, "length", None),
            artwork=artwork,
            author=getattr(playable, "author", None),
            requested_by_id=requester_id,
            requested_by_name=requester_name,
            playable=playable,
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "uri": self.uri,
            "length": self.length,
            "requested_by": self.requested_by_name,
        }
