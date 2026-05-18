"""Typowana konfiguracja aplikacji (pydantic-settings, prefiks NYXIO_)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NYXIO_",
        env_file=".env",
        extra="ignore",
        # Puste zmienne (np. NYXIO_DEV_GUILD_ID=) traktuj jak nieustawione,
        # zamiast próbować je parsować — wraca wtedy wartość domyślna.
        env_ignore_empty=True,
    )

    discord_token: str
    dev_guild_id: int | None = None

    max_queue_size: int = 500
    max_playlist_items: int = 100
    idle_timeout_seconds: int = 180

    redis_url: str | None = None

    lavalink_host: str = "lavalink"
    lavalink_port: int = 2333
    lavalink_password: str = "youshallnotpass"


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
