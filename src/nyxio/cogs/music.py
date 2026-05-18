"""MusicCog — slash-komendy sterujące odtwarzaczem (Lavalink/wavelink)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from nyxio.core.restore import restore_entries, restore_loop
from nyxio.core.track import Track
from nyxio.ui.embeds import queue_embed
from nyxio.utils.errors import NotInVoiceError, QueueFullError
from nyxio.utils.filters import PRESET_NAMES
from nyxio.utils.permissions import is_allowed
from nyxio.utils.query import build_search

if TYPE_CHECKING:
    from nyxio.bot import NyxioBot


def _parse_timestamp(value: str) -> int | None:
    """'mm:ss' / 'h:mm:ss' / 'sekundy' -> ms. None = niepoprawne."""
    value = value.strip()
    try:
        if ":" in value:
            parts = [int(p) for p in value.split(":")]
            secs = 0
            for p in parts:
                secs = secs * 60 + p
        else:
            secs = int(value)
    except ValueError:
        return None
    return max(0, secs) * 1000


class MusicCog(commands.Cog):
    def __init__(self, bot: NyxioBot) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Bramka dostępu stosowana do wszystkich komend tego coga."""
        user = interaction.user
        if not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Komenda działa tylko na serwerze.", ephemeral=True
            )
            return False
        dj_role_id = self.bot.resolve_dj_role_id(user.guild.id)
        if is_allowed(user, dj_role_id):
            return True
        await interaction.response.send_message(
            "⛔ Brak uprawnień — wymagana rola DJ lub uprawnienia administratora.",
            ephemeral=True,
        )
        return False

    @app_commands.command(name="play", description="Odtwórz utwór z YouTube (link lub fraza).")
    @app_commands.describe(query="Link do YouTube lub fraza wyszukiwania")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("Komenda działa tylko na serwerze.")
            return
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.followup.send("Nieobsługiwany kanał.")
            return

        search_query, _ = build_search(query)
        try:
            results = await wavelink.Playable.search(search_query)
        except Exception:  # noqa: BLE001
            await interaction.followup.send("❌ Błąd wyszukiwania (Lavalink).")
            return
        if not results:
            await interaction.followup.send("❌ Brak wyników.")
            return

        max_items = self.bot.settings.max_playlist_items
        if isinstance(results, wavelink.Playlist):
            playables = list(results.tracks)[:max_items]
            label = f"➕ Dodano **{len(playables)}** utworów z playlisty."
        else:
            playables = [results[0]]
            label = f"➕ Dodano: **{results[0].title}**"

        try:
            player = await self.bot.manager.get_or_create(member, channel)
            for playable in playables:
                track = Track.from_playable(playable, member.id, member.display_name)
                await player.enqueue(track)
        except NotInVoiceError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
        except QueueFullError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return

        await interaction.followup.send(label)

    @app_commands.command(name="skip", description="Pomiń bieżący utwór.")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        await player.skip()
        await interaction.response.send_message("⏭️ Pominięto.")

    @app_commands.command(name="previous", description="Wróć do poprzedniego utworu.")
    async def previous(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        if await player.previous():
            await interaction.response.send_message("⏮️ Poprzedni utwór.")
        else:
            await interaction.response.send_message(
                "Brak poprzedniego utworu.", ephemeral=True
            )

    @app_commands.command(name="pause", description="Pauza / wznowienie odtwarzania.")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        paused = await player.pause()
        await player.refresh_ui()
        await interaction.response.send_message("⏸️ Pauza." if paused else "▶️ Wznowiono.")

    @app_commands.command(name="seek", description="Przewiń w utworze (mm:ss lub sekundy).")
    @app_commands.describe(position="Pozycja, np. 1:30 albo 90")
    async def seek(self, interaction: discord.Interaction, position: str) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None or player.queue.current is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        ms = _parse_timestamp(position)
        if ms is None:
            await interaction.response.send_message(
                "Niepoprawny format. Użyj `mm:ss` lub liczby sekund.", ephemeral=True
            )
            return
        length = player.queue.current.length
        if length and ms > length:
            await interaction.response.send_message(
                "Pozycja poza długością utworu.", ephemeral=True
            )
            return
        await player.seek(ms)
        await interaction.response.send_message(f"⏩ Przewinięto do `{position}`.")

    @app_commands.command(name="filter", description="Filtr audio: none/bass/nightcore/eq.")
    @app_commands.describe(preset="Preset filtra")
    @app_commands.choices(
        preset=[app_commands.Choice(name=n, value=n) for n in PRESET_NAMES]
    )
    async def filter_cmd(
        self, interaction: discord.Interaction, preset: app_commands.Choice[str]
    ) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        await player.set_filter(preset.value)
        await interaction.response.send_message(f"🎛️ Filtr: **{preset.value}**")

    @app_commands.command(name="stop", description="Zatrzymaj i rozłącz Nyxio.")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        await player.stop()
        await interaction.response.send_message("⏹️ Zatrzymano.")

    @app_commands.command(name="queue", description="Pokaż kolejkę.")
    async def queue(self, interaction: discord.Interaction, page: int = 1) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Kolejka pusta.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=queue_embed(player.queue, page), ephemeral=True
        )

    @app_commands.command(
        name="wznow", description="Przywróć kolejkę z poprzedniej sesji (po restarcie)."
    )
    async def wznow(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send("Komenda działa tylko na serwerze.")
            return
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.followup.send("Nieobsługiwany kanał.")
            return

        snapshot = await self.bot.manager.state_store.get_queue(
            interaction.guild_id or 0
        )
        entries = restore_entries(snapshot) if snapshot else []
        if not entries:
            await interaction.followup.send("Brak zapisanej sesji do wznowienia.")
            return

        try:
            player = await self.bot.manager.get_or_create(member, channel)
        except NotInVoiceError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return

        restored = 0
        for entry in entries[: self.bot.settings.max_queue_size]:
            try:
                results = await wavelink.Playable.search(entry["uri"])
            except Exception:  # noqa: BLE001
                continue
            if not results or isinstance(results, wavelink.Playlist):
                continue
            track = Track.from_playable(
                results[0], 0, entry.get("requested_by", "—")
            )
            try:
                await player.enqueue(track)
            except QueueFullError:
                break
            restored += 1
        player.queue.loop_mode = restore_loop(snapshot or {})
        await interaction.followup.send(
            f"♻️ Wznowiono **{restored}** utworów z poprzedniej sesji."
            if restored
            else "Nie udało się odtworzyć zapisanych utworów."
        )

    @app_commands.command(name="teraz", description="Pokaż aktualny utwór z paskiem postępu.")
    async def teraz(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        embed = player.now_embed() if player is not None else None
        if embed is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="autoplay", description="Włącz/wyłącz AutoPlay (powiązane utwory).")
    async def autoplay(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        enabled = await player.toggle_autoplay()
        await player.refresh_ui()
        await interaction.response.send_message(
            f"🔀 AutoPlay: **{'włączony' if enabled else 'wyłączony'}**"
        )

    @app_commands.command(name="loop", description="Przełącz tryb pętli (off/utwór/kolejka).")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        mode = player.queue.cycle_loop()
        await player.refresh_ui()
        await interaction.response.send_message(f"🔁 Pętla: **{mode.value}**")

    @app_commands.command(
        name="volume", description="Ustaw głośność 0–200% (bez wartości: pokaż aktualną)."
    )
    @app_commands.describe(level="Poziom głośności w procentach (0–200)")
    async def volume(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 0, 200] | None = None,
    ) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Nic nie jest odtwarzane.", ephemeral=True)
            return
        if level is None:
            await interaction.response.send_message(
                f"🔊 Aktualna głośność: **{player.volume_pct}%**", ephemeral=True
            )
            return
        applied = await player.set_volume(level)
        await player.refresh_ui()
        await interaction.response.send_message(f"🔊 Głośność: **{applied}%**")

    @app_commands.command(name="shuffle", description="Przetasuj kolejkę.")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.bot.manager.get(interaction.guild_id or 0)
        if player is None:
            await interaction.response.send_message("Kolejka pusta.", ephemeral=True)
            return
        player.queue.shuffle()
        await interaction.response.send_message("🔀 Przetasowano.")


async def setup(bot: NyxioBot) -> None:
    await bot.add_cog(MusicCog(bot))
