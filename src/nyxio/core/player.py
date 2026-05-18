"""GuildPlayer — stan i sterowanie odtwarzaniem jednej gildii (Lavalink/wavelink).

Sterowanie zdarzeniowe: koniec utworu przychodzi jako zdarzenie wavelink
(bot.on_wavelink_track_end -> handle_track_end). Brak wątku FFmpeg,
brak pętli z asyncio.Event. Kolejka/historia/loop bez zmian (TrackQueue).
"""

from __future__ import annotations

import asyncio
import enum
from typing import TYPE_CHECKING

import discord
import wavelink

from nyxio.core.queue import LoopMode, TrackQueue
from nyxio.core.track import Track
from nyxio.infra.logging import get_logger
from nyxio.utils.errors import QueueFullError
from nyxio.utils.filters import apply_filter_preset

if TYPE_CHECKING:
    from nyxio.core.manager import PlayerManager

log = get_logger("player")

# Reasony końca utworu, po których NIE przewijamy dalej (sami wywołaliśmy play).
_NO_ADVANCE = {"replaced", "cleanup"}

# Ile kolejnych nieudanych prób odtworzenia tolerujemy w jednym przejściu
# kolejki, zanim odpuścimy i powiadomimy kanał (chroni przed zjedzeniem
# całej kolejki, gdy padł łańcuch YouTube/Lavalink).
_MAX_PLAY_FAILURES = 3


class PlayerState(enum.Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class GuildPlayer:
    def __init__(
        self,
        guild_id: int,
        player: wavelink.Player,
        text_channel: discord.abc.Messageable,
        manager: PlayerManager,
    ) -> None:
        self.guild_id = guild_id
        self.player = player
        self.text_channel = text_channel
        self._manager = manager

        self.queue = TrackQueue(max_size=manager.settings.max_queue_size)
        self.state = PlayerState.IDLE
        self.now_playing_message: discord.Message | None = None
        self.volume_pct = manager.guild_config.get_default_volume(guild_id)
        self.autoplay = manager.guild_config.get_autoplay(guild_id)
        self._idle_task: asyncio.Task[None] | None = None
        self._last_track: Track | None = None
        # Serializuje _advance: zdarzenia track_end i bezpośrednie wywołania
        # (skip/previous/enqueue) nie mogą równolegle wołać queue.get_next().
        self._advance_lock = asyncio.Lock()
        # Trzymamy referencję do fire-and-forget snapshotu, by GC go nie ubił.
        self._persist_task: asyncio.Task[None] | None = None

    # ---- Właściwości pomocnicze -------------------------------------------

    @property
    def voice_channel(self) -> discord.VoiceChannel | discord.StageChannel | None:
        return self.player.channel

    @property
    def position_ms(self) -> int:
        if not (self.player.playing or self.player.paused):
            return 0
        return int(self.player.position or 0)

    @property
    def is_paused(self) -> bool:
        return bool(self.player.paused)

    async def toggle_autoplay(self) -> bool:
        self.autoplay = not self.autoplay
        await self._manager.guild_config.set_autoplay(self.guild_id, self.autoplay)
        return self.autoplay

    # ---- API komend -------------------------------------------------------

    async def enqueue(self, track: Track) -> None:
        self.queue.add(track)
        self._persist()
        if not self.player.playing and self.state is not PlayerState.PAUSED:
            await self._advance()

    async def skip(self) -> None:
        if self.player.playing or self.player.paused:
            await self.player.stop()  # -> track_end(stopped) -> _advance
        self._persist()

    async def previous(self) -> bool:
        """Cofa do poprzedniego utworu. False = brak historii."""
        if not self.queue.previous():
            return False
        if self.player.playing or self.player.paused:
            await self.player.stop()  # -> track_end -> _advance pobierze poprzedni
        else:
            await self._advance()
        self._persist()
        return True

    def shuffle(self) -> None:
        self.queue.shuffle()
        self._persist()

    def cycle_loop(self) -> LoopMode:
        mode = self.queue.cycle_loop()
        self._persist()
        return mode

    async def pause(self) -> bool:
        if self.player.playing and not self.player.paused:
            await self.player.pause(True)
            self.state = PlayerState.PAUSED
            return True
        if self.player.paused:
            await self.player.pause(False)
            self.state = PlayerState.PLAYING
            return False
        return False

    async def set_volume(self, percent: int) -> int:
        clamped = max(0, min(200, percent))
        self.volume_pct = clamped
        await self.player.set_volume(clamped)
        await self._manager.guild_config.set_default_volume(self.guild_id, clamped)
        return clamped

    async def seek(self, position_ms: int) -> None:
        await self.player.seek(max(0, position_ms))

    async def set_filter(self, preset: str) -> None:
        await apply_filter_preset(self.player, preset)

    async def stop(self) -> None:
        self.queue.clear()
        self.state = PlayerState.STOPPED
        await self._manager.teardown(self.guild_id)

    # ---- Sterowanie zdarzeniowe -------------------------------------------

    async def handle_track_end(self, reason: str) -> None:
        norm = reason.split(".")[-1].lower()  # 'TrackEndReason.finished' -> 'finished'
        if norm in _NO_ADVANCE:
            return
        await self._advance()

    async def _advance(self) -> None:
        async with self._advance_lock:
            failures = 0
            while True:
                track = self.queue.get_next()
                if track is None and self.autoplay and await self._try_autoplay():
                    track = self.queue.get_next()
                if track is None:
                    self.state = PlayerState.IDLE
                    self._arm_idle_timeout()
                    return
                self._cancel_idle_timeout()
                try:
                    await self.player.play(track.playable, volume=self.volume_pct)
                except Exception:  # noqa: BLE001
                    log.exception(
                        "play_failed", guild_id=self.guild_id, title=track.title
                    )
                    failures += 1
                    if failures >= _MAX_PLAY_FAILURES:
                        self.state = PlayerState.IDLE
                        self._arm_idle_timeout()
                        await self._notify_playback_error()
                        return
                    continue  # spróbuj kolejny utwór z kolejki
                self._last_track = track
                self.state = PlayerState.PLAYING
                await self._publish_now_playing(track)
                return

    async def _notify_playback_error(self) -> None:
        try:
            await self.text_channel.send(
                "❌ Nie udało się odtworzyć utworów — problem z YouTube/Lavalink. "
                "Spróbuj ponownie za chwilę."
            )
        except discord.HTTPException:
            pass

    async def _try_autoplay(self) -> bool:
        """Dograj powiązane utwory (YouTube Mix z ostatniego). True = dodano.

        Własna kolejka — nie używamy natywnego autoplay wavelink; budujemy
        mini-radio z ID ostatniego utworu. Limit chroni przed pętlą.
        """
        last = self._last_track
        if last is None or last.playable is None:
            return False
        vid = getattr(last.playable, "identifier", None)
        if not vid:
            return False
        mix_url = f"https://www.youtube.com/watch?v={vid}&list=RD{vid}"
        try:
            results = await wavelink.Playable.search(mix_url)
        except Exception:  # noqa: BLE001
            log.warning("autoplay_search_failed", guild_id=self.guild_id)
            return False
        playables = (
            list(results.tracks)
            if isinstance(results, wavelink.Playlist)
            else list(results)
        )
        added = 0
        for pl in playables:
            if getattr(pl, "identifier", None) == vid:
                continue  # pomiń ten sam utwór
            try:
                self.queue.add(
                    Track.from_playable(pl, last.requested_by_id, "AutoPlay")
                )
            except QueueFullError:
                break
            added += 1
            if added >= 5:
                break
        if added:
            log.info("autoplay_queued", guild_id=self.guild_id, count=added)
        return added > 0

    # ---- Idle timeout ------------------------------------------------------

    def _arm_idle_timeout(self) -> None:
        self._cancel_idle_timeout()
        self._idle_task = asyncio.create_task(self._idle_countdown())

    def _cancel_idle_timeout(self) -> None:
        if self._idle_task is not None:
            self._idle_task.cancel()
            self._idle_task = None

    async def _idle_countdown(self) -> None:
        try:
            await asyncio.sleep(self._manager.settings.idle_timeout_seconds)
        except asyncio.CancelledError:
            return
        log.info("idle_timeout", guild_id=self.guild_id)
        await self._manager.teardown(self.guild_id)

    # ---- UI ---------------------------------------------------------------

    async def _publish_now_playing(self, track: Track) -> None:
        from nyxio.ui.controls import ControlsView
        from nyxio.ui.embeds import now_playing_embed

        embed = now_playing_embed(
            track, self.queue, volume_pct=self.volume_pct, autoplay=self.autoplay
        )
        view = ControlsView(self)
        try:
            if self.now_playing_message is not None:
                await self.now_playing_message.delete()
        except discord.HTTPException:
            pass
        self.now_playing_message = await self.text_channel.send(embed=embed, view=view)

    async def refresh_ui(self) -> None:
        from nyxio.ui.controls import ControlsView
        from nyxio.ui.embeds import now_playing_embed

        if self.now_playing_message is None or self.queue.current is None:
            return
        embed = now_playing_embed(
            self.queue.current,
            self.queue,
            state=self.state,
            volume_pct=self.volume_pct,
            autoplay=self.autoplay,
        )
        try:
            await self.now_playing_message.edit(embed=embed, view=ControlsView(self))
        except discord.HTTPException:
            pass

    def now_embed(self) -> discord.Embed | None:
        """Embed z aktualnym paskiem postępu (dla /teraz i przycisku)."""
        from nyxio.ui.embeds import now_playing_embed

        if self.queue.current is None:
            return None
        return now_playing_embed(
            self.queue.current,
            self.queue,
            state=self.state,
            volume_pct=self.volume_pct,
            autoplay=self.autoplay,
            position_ms=self.position_ms,
        )

    # ---- Pomocnicze -------------------------------------------------------

    def _persist(self) -> None:
        # Referencję trzymamy w polu, żeby GC nie ubił taska przed zapisem.
        self._persist_task = asyncio.create_task(
            self._manager.state_store.save_queue(self.guild_id, self.queue.to_snapshot())
        )

    async def shutdown(self) -> None:
        self._cancel_idle_timeout()
        try:
            await self.player.disconnect()
        except Exception:  # noqa: BLE001
            log.warning("disconnect_failed", guild_id=self.guild_id)
        if self.now_playing_message is not None:
            try:
                await self.now_playing_message.edit(
                    content="⏹️ Sesja zakończona.", embed=None, view=None
                )
            except discord.HTTPException:
                pass
