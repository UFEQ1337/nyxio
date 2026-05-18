"""Parsowanie zapytań/URL do wyszukiwania (czysta logika, testowalna).

Decyzja produktowa (bez zmian względem natywnego silnika):
- Mix / Radio (list=RD...)  -> gramy TYLKO kliknięty utwór,
- prawdziwa playlista (PL/album) -> cała (cap po stronie kolejki),
- fraza tekstowa -> wyszukiwanie YouTube.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def is_url(query: str) -> bool:
    try:
        parsed = urlparse(query)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def playlist_id(url: str) -> str | None:
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    values = params.get("list")
    return values[0] if values else None


def is_radio_mix(url: str) -> bool:
    """YouTube Mix/Radio — auto-generowana, w praktyce nieskończona lista."""
    pid = playlist_id(url)
    return pid is not None and pid.startswith("RD")


def is_real_playlist(url: str) -> bool:
    pid = playlist_id(url)
    return pid is not None and not pid.startswith("RD")


def strip_to_video(url: str) -> str:
    """Zostawia sam film (watch?v=ID), odcina list=/index= (dla Mix/Radio)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    params = parse_qs(parsed.query)
    vid = params.get("v", [None])[0]
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return url


def build_search(query: str) -> tuple[str, bool]:
    """Zwraca (zapytanie_dla_wavelink, czy_traktować_jako_playlistę).

    - URL prawdziwej playlisty -> (url, True)
    - URL Mix/Radio            -> (sam film, False)
    - inny URL                 -> (url, False)
    - fraza tekstowa           -> ('ytsearch:fraza', False)
    """
    if is_url(query):
        if is_real_playlist(query):
            return query, True
        if is_radio_mix(query):
            return strip_to_video(query), False
        return query, False
    return f"ytsearch:{query}", False
