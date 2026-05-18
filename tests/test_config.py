"""Testy wczytywania konfiguracji (regresja: puste zmienne env)."""

from __future__ import annotations

from nyxio.config import Settings


def test_empty_optional_env_treated_as_unset(monkeypatch):
    monkeypatch.setenv("NYXIO_DISCORD_TOKEN", "abc")
    monkeypatch.setenv("NYXIO_DEV_GUILD_ID", "")  # puste — nie może wywalić parsowania
    monkeypatch.setenv("NYXIO_REDIS_URL", "")
    s = Settings(_env_file=None)  # ignoruj lokalny .env w teście
    assert s.dev_guild_id is None
    assert s.redis_url is None


def test_values_parsed(monkeypatch):
    monkeypatch.setenv("NYXIO_DISCORD_TOKEN", "abc")
    monkeypatch.setenv("NYXIO_DEV_GUILD_ID", "12345")
    s = Settings(_env_file=None)
    assert s.dev_guild_id == 12345
