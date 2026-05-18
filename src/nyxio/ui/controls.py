"""ControlsView — interaktywne przyciski sterujące odtwarzaczem.

Autoryzacja: klikający musi być na tym samym kanale głosowym co bot.
Układ: 3 rzędy (limit Discorda 5 przycisków/rząd).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from nyxio.ui.embeds import queue_embed

if TYPE_CHECKING:
    from nyxio.core.player import GuildPlayer


class ControlsView(discord.ui.View):
    def __init__(self, player: GuildPlayer) -> None:
        super().__init__(timeout=None)
        self._player = player
        # Przycisk AutoPlay odzwierciedla aktualny stan kolorem.
        self.autoplay_btn.style = (
            discord.ButtonStyle.success
            if player.autoplay
            else discord.ButtonStyle.secondary
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        channel = self._player.voice_channel
        if (
            isinstance(user, discord.Member)
            and user.voice is not None
            and channel is not None
            and user.voice.channel == channel
        ):
            return True
        await interaction.response.send_message(
            "Musisz być na tym samym kanale głosowym co Nyxio.", ephemeral=True
        )
        return False

    # ---- Rząd 0: transport -------------------------------------------------

    @discord.ui.button(label="Poprzedni", emoji="⏮️", row=0)
    async def previous(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        if not await self._player.previous():
            await interaction.followup.send("Brak poprzedniego utworu.", ephemeral=True)

    @discord.ui.button(
        label="Pauza", emoji="⏯️", style=discord.ButtonStyle.primary, row=0
    )
    async def pause_resume(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        await self._player.pause()
        await self._player.refresh_ui()

    @discord.ui.button(label="Następny", emoji="⏭️", row=0)
    async def skip(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        await self._player.skip()

    @discord.ui.button(
        label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, row=0
    )
    async def stop_playback(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        await self._player.stop()

    @discord.ui.button(label="Pętla", emoji="🔁", row=0)
    async def loop(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        self._player.queue.cycle_loop()
        await self._player.refresh_ui()

    # ---- Rząd 1: dźwięk + kolejka + teraz ----------------------------------

    @discord.ui.button(label="Ciszej", emoji="🔉", row=1)
    async def volume_down(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        await self._player.set_volume(self._player.volume_pct - 10)
        await self._player.refresh_ui()

    @discord.ui.button(label="Głośniej", emoji="🔊", row=1)
    async def volume_up(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        await self._player.set_volume(self._player.volume_pct + 10)
        await self._player.refresh_ui()

    @discord.ui.button(label="Losuj", emoji="🔀", row=1)
    async def shuffle(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        self._player.queue.shuffle()
        await interaction.followup.send("🔀 Przetasowano.", ephemeral=True)

    @discord.ui.button(label="Kolejka", emoji="📜", row=1)
    async def show_queue(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.send_message(
            embed=queue_embed(self._player.queue), ephemeral=True
        )

    @discord.ui.button(label="Teraz", emoji="🕒", row=1)
    async def now(
        self, interaction: discord.Interaction, _: discord.ui.Button[ControlsView]
    ) -> None:
        embed = self._player.now_embed()
        if embed is None:
            await interaction.response.send_message(
                "Nic nie jest odtwarzane.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---- Rząd 2: AutoPlay --------------------------------------------------

    @discord.ui.button(label="AutoPlay", emoji="▶️", row=2)
    async def autoplay_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button[ControlsView]
    ) -> None:
        await interaction.response.defer()
        enabled = await self._player.toggle_autoplay()
        button.style = (
            discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        )
        await self._player.refresh_ui()
