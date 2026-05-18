"""SettingsCog — runtime'owa konfiguracja per-gildia (grupa /dj).

Dostęp: tylko osoby z uprawnieniem "Zarządzanie serwerem".
Egzekwowane natywnie (default_permissions — widoczne w Integracjach
Discorda) oraz twardym checkiem w kodzie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from nyxio.bot import NyxioBot


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class DJGroup(app_commands.Group):
    def __init__(self, bot: NyxioBot) -> None:
        super().__init__(name="dj", description="Konfiguracja roli DJ dla tego serwera.")
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if isinstance(user, discord.Member) and user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(
            "⛔ Wymagane uprawnienie *Zarządzanie serwerem*.", ephemeral=True
        )
        return False

    @app_commands.command(name="set", description="Ustaw rolę DJ dla tego serwera.")
    @app_commands.describe(role="Rola, której posiadacze mogą sterować muzyką")
    async def set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild_id is not None
        await self.bot.guild_config.set_dj_role_id(interaction.guild_id, role.id)
        await interaction.response.send_message(
            f"✅ Rola DJ ustawiona na {role.mention}. "
            "Administratorzy zawsze zachowują dostęp.",
            ephemeral=True,
        )

    @app_commands.command(name="clear", description="Usuń rolę DJ (dostęp dla każdego).")
    async def clear_role(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await self.bot.guild_config.set_dj_role_id(interaction.guild_id, None)
        await interaction.response.send_message(
            "✅ Rola DJ usunięta — komend muzycznych może używać każdy.",
            ephemeral=True,
        )

    @app_commands.command(name="show", description="Pokaż aktualną rolę DJ.")
    async def show_role(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        role_id = self.bot.resolve_dj_role_id(interaction.guild.id)
        if role_id is None:
            msg = "Rola DJ nie jest ustawiona — dostęp dla każdego."
        else:
            role = interaction.guild.get_role(role_id)
            label = role.mention if role is not None else f"`{role_id}` (rola usunięta?)"
            msg = f"Aktualna rola DJ: {label}"
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: NyxioBot) -> None:
    bot.tree.add_command(DJGroup(bot))
