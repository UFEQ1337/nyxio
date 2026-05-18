"""Entrypoint: wczytanie konfiguracji, konfiguracja logów, start bota."""

from __future__ import annotations

from nyxio.bot import NyxioBot
from nyxio.config import load_settings
from nyxio.infra.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = load_settings()
    bot = NyxioBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
