"""Testy parsowania zapytań/URL (czyste, bez sieci)."""

from __future__ import annotations

from nyxio.utils.query import (
    build_search,
    is_radio_mix,
    is_real_playlist,
    is_url,
    strip_to_video,
)

_VIDEO = "https://www.youtube.com/watch?v=abc123"
_MIX = "https://www.youtube.com/watch?v=abc123&list=RDMMabc123&index=2"
_PLAYLIST = "https://www.youtube.com/playlist?list=PLxyz"
_VIDEO_IN_PL = "https://www.youtube.com/watch?v=abc123&list=PLxyz"


def test_is_url():
    assert is_url(_VIDEO)
    assert not is_url("jakas fraza do wyszukania")
    assert not is_url("")


def test_radio_mix_detection():
    assert is_radio_mix(_MIX)
    assert not is_radio_mix(_VIDEO)
    assert not is_radio_mix(_PLAYLIST)


def test_real_playlist_detection():
    assert is_real_playlist(_PLAYLIST)
    assert is_real_playlist(_VIDEO_IN_PL)
    assert not is_real_playlist(_MIX)
    assert not is_real_playlist(_VIDEO)


def test_strip_to_video():
    assert strip_to_video(_MIX) == "https://www.youtube.com/watch?v=abc123"
    assert strip_to_video(_VIDEO) == "https://www.youtube.com/watch?v=abc123"


def test_build_search_text():
    q, is_pl = build_search("never gonna give you up")
    assert q == "ytsearch:never gonna give you up"
    assert is_pl is False


def test_build_search_mix_strips_to_video():
    q, is_pl = build_search(_MIX)
    assert q == "https://www.youtube.com/watch?v=abc123"
    assert is_pl is False


def test_build_search_real_playlist():
    q, is_pl = build_search(_PLAYLIST)
    assert q == _PLAYLIST
    assert is_pl is True


def test_build_search_plain_video_url():
    q, is_pl = build_search(_VIDEO)
    assert q == _VIDEO
    assert is_pl is False


def test_build_search_soundcloud_url_passthrough():
    """SoundCloud URL idzie surowy do Lavalink (sources.soundcloud=true),
    nie opakowujemy go w ytsearch:."""
    sc = "https://soundcloud.com/artist/track-name"
    q, is_pl = build_search(sc)
    assert q == sc
    assert is_pl is False
    assert not q.startswith("ytsearch:")
