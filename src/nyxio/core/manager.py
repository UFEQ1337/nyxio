"""PlayerManager — registry/lifecycle odtwarzaczy per gildia (Lavalink/wavelink)."""

from __future__ import annotations

import asyncio

import discord
import wavelink

from nyxio.config import Settings
from nyxio.core.guild_config import GuildConfigStore
from nyxio.core.player import GuildPlayer
from nyxio.infra.logging import get_logger
from nyxio.infra.state_store import StateStore
from nyxio.utils.errors import NotInVoiceError

log = get_logger("manager")


class PlayerManager:
    def __init__(self, settings: Settings, guild_config: GuildConfigStore) -> None:
        self.settings = settings
        self.guild_config = guild_config
        self.state_store = StateStore(settings.redis_url)
        self._players: dict[int, GuildPlayer] = {}
        self._lock = asyncio.Lock()

    def get(self, guild_id: int) -> GuildPlayer | None:
        return self._players.get(guild_id)

    async def get_or_create(
        self,
        member: discord.Member,
        text_channel: discord.abc.Messageable,
    ) -> GuildPlayer:
        guild = member.guild
        async with self._lock:
            existing = self._players.get(guild.id)
            if existing is not None:
                return existing

            if member.voice is None or member.voice.channel is None:
                raise NotInVoiceError("Dołącz najpierw do kanału głosowego.")

            voice = await member.voice.channel.connect(
                cls=wavelink.Player, self_deaf=True
            )
            player = GuildPlayer(guild.id, voice, text_channel, self)
            self._players[guild.id] = player
            log.info("player_created", guild_id=guild.id)
            return player

    async def teardown(self, guild_id: int, *, clear_state: bool = True) -> None:
        player = self._players.pop(guild_id, None)
        if player is None:
            return
        log.info("player_teardown", guild_id=guild_id, clear_state=clear_state)
        await player.shutdown()
        # clear_state=False przy gracefulnym restarcie procesu — snapshot
        # ma przetrwać, żeby /wznow odzyskał kolejkę. Świadome /stop oraz
        # idle-timeout dalej czyszczą (clear_state=True).
        if clear_state:
            await self.state_store.clear_queue(guild_id)

    async def shutdown_all(self) -> None:
        for guild_id in list(self._players):
            await self.teardown(guild_id, clear_state=False)
        await self.state_store.close()
