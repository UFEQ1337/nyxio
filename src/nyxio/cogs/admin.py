"""AdminCog — diagnostyka i synchronizacja komend."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from nyxio.ui.embeds import help_embed

if TYPE_CHECKING:
    from nyxio.bot import NyxioBot


class AdminCog(commands.Cog):
    def __init__(self, bot: NyxioBot) -> None:
        self.bot = bot

    @app_commands.command(name="pomoc", description="Lista komend Nyxio.")
    async def pomoc(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=help_embed(), ephemeral=True)

    @app_commands.command(name="ping", description="Sprawdź czy Nyxio żyje.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! `{latency_ms} ms`")

    @app_commands.command(name="resync", description="Wymuś resynchronizację komend (właściciel).")
    async def resync(self, interaction: discord.Interaction) -> None:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "⛔ Tylko właściciel bota.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(f"Zsynchronizowano {len(synced)} komend.")


async def setup(bot: NyxioBot) -> None:
    await bot.add_cog(AdminCog(bot))
