"""NyxioBot — podklasa commands.Bot: setup_hook, Lavalink (wavelink), lifecycle."""

from __future__ import annotations

import asyncio

import discord
import wavelink
from discord.ext import commands

from nyxio.config import Settings
from nyxio.core.guild_config import GuildConfigStore
from nyxio.core.manager import PlayerManager
from nyxio.infra.logging import get_logger

log = get_logger("bot")

_EXTENSIONS = ("nyxio.cogs.music", "nyxio.cogs.admin", "nyxio.cogs.settings")


class NyxioBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True  # jedyna potrzebna intencja (nieprzywilejowana)
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.guild_config = GuildConfigStore()
        self.manager = PlayerManager(settings, self.guild_config)

    def resolve_dj_role_id(self, guild_id: int) -> int | None:
        """Rola DJ konfigurowana per-serwer komendą /dj. Brak = dostęp dla każdego."""
        return self.guild_config.get_dj_role_id(guild_id)

    async def _connect_lavalink(self) -> None:
        """Łączy węzeł Lavalink z retry/backoff (JVM może jeszcze wstawać)."""
        uri = f"http://{self.settings.lavalink_host}:{self.settings.lavalink_port}"
        delay = 3
        for attempt in range(1, 11):
            try:
                node = wavelink.Node(uri=uri, password=self.settings.lavalink_password)
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

    async def setup_hook(self) -> None:
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
        if payload.player is None or payload.player.guild is None:
            return
        log.warning(
            "lavalink_track_exception",
            guild_id=payload.player.guild.id,
            error=str(getattr(payload, "exception", "")),
        )
        gplayer = self.manager.get(payload.player.guild.id)
        if gplayer is not None:
            await gplayer.handle_track_end("loadFailed")

    async def on_wavelink_track_stuck(
        self, payload: wavelink.TrackStuckEventPayload
    ) -> None:
        if payload.player is None or payload.player.guild is None:
            return
        log.warning("lavalink_track_stuck", guild_id=payload.player.guild.id)
        gplayer = self.manager.get(payload.player.guild.id)
        if gplayer is not None:
            await gplayer.handle_track_end("stuck")

    # ---- Auto-rozłączenie --------------------------------------------------

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        gplayer = self.manager.get(member.guild.id)
        if gplayer is None:
            return
        channel = gplayer.voice_channel
        if channel is None:
            return
        if not [m for m in channel.members if not m.bot]:
            log.info("alone_in_channel", guild_id=member.guild.id)
            await self.manager.teardown(member.guild.id)

    async def close(self) -> None:
        await self.manager.shutdown_all()
        await super().close()
