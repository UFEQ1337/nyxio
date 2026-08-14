"""NyxioBot — podklasa commands.Bot: setup_hook, Lavalink (wavelink), lifecycle."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import discord
import wavelink
from discord.ext import commands

from nyxio.config import Settings
from nyxio.core.guild_config import GuildConfigStore
from nyxio.core.manager import PlayerManager
from nyxio.infra.logging import get_logger

log = get_logger("bot")

_EXTENSIONS = ("nyxio.cogs.music", "nyxio.cogs.admin", "nyxio.cogs.settings")

# Plik dotykany dopóki bot ma żywe połączenie z Discordem — czyta go
# HEALTHCHECK z Dockerfile. Poprzedni healthcheck (`python -c "import nyxio"`)
# uruchamiał świeży proces i przechodził nawet wtedy, gdy bot wisiał
# rozłączony, czyli dawał fałszywe poczucie bezpieczeństwa.
HEARTBEAT_PATH = Path("/tmp/nyxio.healthy")  # noqa: S108
_HEARTBEAT_INTERVAL_S = 20


class NyxioBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True  # jedyna potrzebna intencja (nieprzywilejowana)
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.guild_config = GuildConfigStore()
        self.manager = PlayerManager(settings, self.guild_config)
        self._heartbeat_task: asyncio.Task[None] | None = None

    def resolve_dj_role_id(self, guild_id: int) -> int | None:
        """Rola DJ konfigurowana per-serwer komendą /dj. Brak = dostęp dla każdego."""
        return self.guild_config.get_dj_role_id(guild_id)

    async def _connect_lavalink(self) -> None:
        """Łączy węzeł Lavalink z retry/backoff (JVM może jeszcze wstawać).

        Po wyczerpaniu prob rzucamy RuntimeError — bez backendu komendy
        zwracaja niejasne bledy. Lepiej wywalic setup_hook i pozwolic
        dockerowi (restart: unless-stopped) zrobic kolejne podejscie.
        """
        uri = f"http://{self.settings.lavalink_host}:{self.settings.lavalink_port}"
        delay = 3
        for attempt in range(1, 11):
            try:
                # resume_timeout=60 — wavelink/Lavalink podtrzymuje sesje
                # przez 60s po rozlaczeniu, dzieki czemu krotki restart
                # Lavalinka nie urywa odtwarzania.
                node = wavelink.Node(
                    uri=uri,
                    password=self.settings.lavalink_password,
                    resume_timeout=60,
                )
                await wavelink.Pool.connect(client=self, nodes=[node])
                log.info("lavalink_connected", uri=uri, attempt=attempt)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "lavalink_connect_retry",
                    attempt=attempt,
                    error=str(exc),
                    retry_in=delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
        log.error("lavalink_connect_failed", uri=uri)
        raise RuntimeError(
            f"Lavalink niedostepny po 10 probach ({uri}) — przerywam start bota."
        )

    @staticmethod
    def _touch_heartbeat() -> None:
        HEARTBEAT_PATH.write_text(str(time.time()), encoding="utf-8")

    async def _heartbeat(self) -> None:
        """Dotyka pliku, dopóki gateway faktycznie odpowiada."""
        while not self.is_closed():
            try:
                # NaN != NaN — latency jest NaN, dopóki nie ma pomiaru z gatewaya.
                if self.is_ready() and self.latency == self.latency:
                    # Zapis w wątku: nie blokujemy event loopu I/O na dysku.
                    await asyncio.to_thread(self._touch_heartbeat)
            except OSError:
                log.warning("heartbeat_write_failed")
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)

    async def setup_hook(self) -> None:
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        await self.guild_config.load()
        await self.manager.state_store.connect()
        await self._connect_lavalink()
        for ext in _EXTENSIONS:
            await self.load_extension(ext)
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("commands_synced_dev", guild_id=self.settings.dev_guild_id)
        else:
            await self.tree.sync()
            log.info("commands_synced_global")

    async def on_ready(self) -> None:
        log.info("ready", user=str(self.user), guilds=len(self.guilds))

    # ---- Zdarzenia wavelink ------------------------------------------------

    async def on_wavelink_node_ready(
        self, payload: wavelink.NodeReadyEventPayload
    ) -> None:
        log.info("lavalink_node_ready", node=payload.node.identifier)

    async def on_wavelink_track_start(
        self, payload: wavelink.TrackStartEventPayload
    ) -> None:
        if payload.player is None or payload.player.guild is None:
            return
        gplayer = self.manager.get(payload.player.guild.id)
        if gplayer is not None:
            await gplayer.handle_track_start()

    async def on_wavelink_track_end(
        self, payload: wavelink.TrackEndEventPayload
    ) -> None:
        if payload.player is None or payload.player.guild is None:
            return
        gplayer = self.manager.get(payload.player.guild.id)
        if gplayer is not None:
            await gplayer.handle_track_end(str(payload.reason))

    async def on_wavelink_track_exception(
        self, payload: wavelink.TrackExceptionEventPayload
    ) -> None:
        """Tylko log — kolejkę przewija wyłącznie on_wavelink_track_end.

        Lavalink przy nieudanym utworze wysyła DWA zdarzenia: TrackException,
        a zaraz po nim TrackEnd(reason=loadFailed). Wołanie _advance z obu
        miejsc zjadało po dwie pozycje na jeden błąd i podwajało tempo pętli.

        Logujemy sam komunikat, nie cały payload: pełny stack trace z Javy to
        kilkanaście kB, a wavelink i tak wypisuje własną kopię (wyciszoną
        w configure_logging).
        """
        if payload.player is None or payload.player.guild is None:
            return
        exc = payload.exception or {}
        message = str(exc.get("message") or "").strip()
        log.warning(
            "lavalink_track_exception",
            guild_id=payload.player.guild.id,
            severity=exc.get("severity"),
            # Pierwsza linia to właściwy powód ("Sign in to confirm you're not
            # a bot", "This video requires login"...); reszta to stack z Javy.
            cause=message.splitlines()[0][:200] if message else "",
        )

    async def on_wavelink_track_stuck(
        self, payload: wavelink.TrackStuckEventPayload
    ) -> None:
        """Zablokowany utwór ubijamy — stop() wygeneruje TrackEnd(stopped),
        czyli jedną, wspólną ścieżkę przewijania kolejki."""
        if payload.player is None or payload.player.guild is None:
            return
        log.warning("lavalink_track_stuck", guild_id=payload.player.guild.id)
        gplayer = self.manager.get(payload.player.guild.id)
        if gplayer is not None:
            # stop() da TrackEnd(stopped), które nie liczy się jako porażka —
            # a zablokowany utwór nią jest. Bez tego seria stucków omijałaby
            # limit i wracała pętla.
            gplayer.note_failure()
        try:
            await payload.player.stop()
        except Exception:  # noqa: BLE001
            log.warning("stuck_stop_failed", guild_id=payload.player.guild.id)

    # ---- Auto-rozłączenie --------------------------------------------------

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        gplayer = self.manager.get(member.guild.id)
        if gplayer is None:
            return
        # Rozłączenie SAMEGO bota (kick z kanału, move, zerwana sesja głosowa).
        # Bez tego player zostawał w rejestrze z martwym voice clientem, a
        # każde kolejne /play dostawało go z cache i nic nie grało.
        if self.user is not None and member.id == self.user.id:
            if after.channel is None:
                log.info("bot_disconnected_from_voice", guild_id=member.guild.id)
                await self.manager.teardown(member.guild.id)
            return
        if member.bot:
            return
        channel = gplayer.voice_channel
        if channel is None:
            return
        if not [m for m in channel.members if not m.bot]:
            log.info("alone_in_channel", guild_id=member.guild.id)
            await self.manager.teardown(member.guild.id)

    async def close(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        await asyncio.to_thread(HEARTBEAT_PATH.unlink, True)
        await self.manager.shutdown_all()
        await super().close()
