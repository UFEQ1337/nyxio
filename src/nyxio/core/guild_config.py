"""Trwała konfiguracja per-gildia (rola DJ itp.).

Uniwersalne podejście stosowane w dojrzałych botach: ustawienia są
zmieniane komendą w trakcie działania i trwale zapisywane, a nie
wczytywane ze środowiska przy starcie.

Backend: plik JSON z atomowym zapisem (replace), serializacja pod
asyncio.Lock. Bez dodatkowych zależności; przy skali 50–1000 gildii
wystarczający. Ścieżka migracji do SQLite/Redis pozostaje otwarta
(wystarczy podmienić implementację get/set).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from nyxio.infra.logging import get_logger

log = get_logger("guild_config")


class GuildConfigStore:
    def __init__(self, path: str = "data/guild_config.json") -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._data: dict[str, dict[str, Any]] = {}

    async def load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            log.info("guild_config_loaded", guilds=len(self._data))
        except (OSError, json.JSONDecodeError):
            log.exception("guild_config_load_failed")
            self._data = {}

    def get_dj_role_id(self, guild_id: int) -> int | None:
        value = self._data.get(str(guild_id), {}).get("dj_role_id")
        return int(value) if value is not None else None

    async def set_dj_role_id(self, guild_id: int, role_id: int | None) -> None:
        async with self._lock:
            entry = self._data.setdefault(str(guild_id), {})
            if role_id is None:
                entry.pop("dj_role_id", None)
            else:
                entry["dj_role_id"] = role_id
            await self._persist()

    def get_default_volume(self, guild_id: int) -> int:
        """Domyślna głośność serwera w procentach (0–200). Brak = 100."""
        value = self._data.get(str(guild_id), {}).get("default_volume")
        return int(value) if value is not None else 100

    async def set_default_volume(self, guild_id: int, volume: int) -> None:
        async with self._lock:
            entry = self._data.setdefault(str(guild_id), {})
            entry["default_volume"] = volume
            await self._persist()

    def get_autoplay(self, guild_id: int) -> bool:
        """Czy AutoPlay włączony dla serwera. Brak = False."""
        return bool(self._data.get(str(guild_id), {}).get("autoplay", False))

    async def set_autoplay(self, guild_id: int, enabled: bool) -> None:
        async with self._lock:
            entry = self._data.setdefault(str(guild_id), {})
            entry["autoplay"] = enabled
            await self._persist()

    async def _persist(self) -> None:
        # Blokujący zapis offloadowany do wątku — nie blokuje event loop.
        snapshot = json.dumps(self._data, ensure_ascii=False, indent=2)
        await asyncio.to_thread(self._write_sync, snapshot)

    def _write_sync(self, payload: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self._path)  # atomowa podmiana
        except OSError:
            log.exception("guild_config_flush_failed")
            Path(tmp).unlink(missing_ok=True)
