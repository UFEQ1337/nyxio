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
    from nyxio.ui.controls import ControlsView

log = get_logger("player")

# Reasony końca utworu, po których NIE przewijamy dalej (sami wywołaliśmy play).
_NO_ADVANCE = {"replaced", "cleanup"}

# Reasony oznaczające, że utwór NIE zagrał (błąd źródła/dekodera). Lavalink
# wysyła je jako TrackEndEvent po TrackExceptionEvent — liczymy je jako porażki.
_FAILURE_REASONS = {"loadfailed", "stuck"}

# Ile KOLEJNYCH nieudanych utworów tolerujemy, zanim odpuścimy i powiadomimy
# kanał. Licznik jest polem instancji (nie zmienną lokalną _advance), bo błąd
# odtwarzania przychodzi asynchronicznie — zdarzeniem, już po tym jak
# player.play() zwrócił sukces. Zeruje go dopiero potwierdzony start utworu.
_MAX_CONSECUTIVE_FAILURES = 3

# Ile powiązanych utworów dokłada jeden przebieg AutoPlay.
_AUTOPLAY_BATCH = 5

# Od jakiej pozycji w utworze uznajemy odtwarzanie za potwierdzone. Lavalink
# przysyła pozycję co `playerUpdateInterval` sekund (application.yml).
_PLAYBACK_CONFIRMED_MS = 1000


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
        # Trzymamy referencje do fire-and-forget snapshotów, by GC ich nie ubił.
        # Zbiór, nie pojedyncze pole — inaczej kolejny _persist() nadpisywał
        # referencję i poprzedni, jeszcze trwający zapis tracił jedynego
        # właściciela (dokładnie to, czemu miało zapobiegać).
        self._persist_tasks: set[asyncio.Task[None]] = set()
        # Liczba kolejnych utworów, które nie zagrały (loadFailed/stuck).
        self._consecutive_failures = 0
        # Czy w tej sesji cokolwiek faktycznie zagrało. AutoPlay bez tego
        # potrafił budować mini-radio z utworu, który sam nigdy nie ruszył.
        self._had_successful_start = False
        # Jedna instancja widoku na gracza — discord.py trzyma widoki z
        # timeout=None w rejestrze bez końca, więc nowy obiekt przy każdym
        # odświeżeniu UI był wyciekiem pamięci.
        self._controls_view: ControlsView | None = None

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

    async def enqueue_many(self, tracks: list[Track], *, to_front: bool = False) -> int:
        """Dodaj wiele utworow naraz; _advance odpala raz na koncu (inaczej
        pierwszy wstawiony zacznie grac, zanim wstawimy reszte playlisty).
        to_front=True wstawia na poczatek kolejki zachowujac kolejnosc.
        Zwraca ile faktycznie dodano (best-effort przy pelnej kolejce)."""
        # reversed + add_next zostawia pierwszy utwor na samym przodzie kolejki.
        seq = list(reversed(tracks)) if to_front else tracks
        added = 0
        for track in seq:
            try:
                self.queue.add_next(track) if to_front else self.queue.add(track)
            except QueueFullError:
                break
            added += 1
        self._persist()
        if not self.player.playing and self.state is not PlayerState.PAUSED:
            await self._advance()
        return added

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

    async def handle_track_start(self) -> None:
        """Lavalink zaczął obsługiwać utwór — publikujemy UI.

        UWAGA: to zdarzenie NIE jest dowodem, że cokolwiek zagrało. Lavalink
        wysyła je, zanim lavaplayer rozwiąże format strumienia, więc dostajemy
        je także dla utworów, które zaraz potem poleca z loadFailed. Zerowanie
        licznika porażek w tym miejscu kasowało go między kolejnymi bledami
        ("consecutive": 1 w kółko) i pętla wracała. Sukces potwierdza dopiero
        handle_progress().
        """
        self.state = PlayerState.PLAYING
        track = self.queue.current
        if track is not None:
            await self._publish_now_playing(track)

    def handle_progress(self, position_ms: int) -> None:
        """Pozycja w utworze rośnie — czyli audio faktycznie płynie.

        To jedyny wiarygodny sygnał, że łańcuch YouTube -> Lavalink -> Discord
        działa. Dopiero on zeruje licznik porażek i odblokowuje AutoPlay.
        """
        if position_ms <= _PLAYBACK_CONFIRMED_MS:
            return
        if not self._had_successful_start or self._consecutive_failures:
            log.info("playback_confirmed", guild_id=self.guild_id)
        self._consecutive_failures = 0
        self._had_successful_start = True

    def note_failure(self, reason: str = "stuck") -> None:
        """Odnotuj utwór, który nie zagrał (wołane też z handlera stuck)."""
        self._consecutive_failures += 1
        log.warning(
            "track_failed",
            guild_id=self.guild_id,
            reason=reason,
            consecutive=self._consecutive_failures,
        )

    async def handle_track_end(self, reason: str) -> None:
        norm = reason.split(".")[-1].lower()  # 'TrackEndReason.finished' -> 'finished'
        if norm in _NO_ADVANCE:
            return
        if norm in _FAILURE_REASONS:
            self.note_failure(norm)
        elif norm == "finished":
            # Utwór dograł do końca — mocniejszy dowód niż pozycja > 1 s.
            self._consecutive_failures = 0
            self._had_successful_start = True
        await self._advance()

    def _can_autoplay(self) -> bool:
        """AutoPlay tylko gdy łańcuch odtwarzania faktycznie działa.

        Bez tego warunku pusta po serii błędów kolejka była w kółko
        dopełniana Mixem z niegrywalnego wideo — bot sam generował setki
        żądań do YouTube i nakręcał wykrywanie bota.
        """
        return self.autoplay and self._had_successful_start and self._consecutive_failures == 0

    async def _advance(self) -> None:
        async with self._advance_lock:
            while True:
                if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    log.warning(
                        "playback_failure_limit",
                        guild_id=self.guild_id,
                        failures=self._consecutive_failures,
                    )
                    # Zerujemy, żeby ręczne /skip albo /play mogło spróbować
                    # ponownie — ale kolejki dalej sami nie przewijamy.
                    self._consecutive_failures = 0
                    self.state = PlayerState.IDLE
                    self._arm_idle_timeout()
                    await self._notify_playback_error()
                    return
                track = self.queue.get_next()
                if track is None and self._can_autoplay() and await self._try_autoplay():
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
                    self._consecutive_failures += 1
                    continue  # spróbuj kolejny utwór z kolejki
                self._last_track = track
                self.state = PlayerState.PLAYING
                return

    async def _notify_playback_error(self) -> None:
        try:
            await self.text_channel.send(
                "❌ Nie udało się odtworzyć utworów — problem z YouTube/Lavalink. "
                "Spróbuj ponownie za chwilę."
            )
        except discord.NotFound:
            log.info("text_channel_gone", guild_id=self.guild_id)
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
                # requested_by_id=0 — inaczej embed oznaczał pierwotnego
                # zamawiającego, a etykieta "AutoPlay" nigdy się nie pokazywała.
                self.queue.add(Track.from_playable(pl, 0, "AutoPlay"))
            except QueueFullError:
                break
            added += 1
            if added >= _AUTOPLAY_BATCH:
                break
        if added:
            log.info("autoplay_queued", guild_id=self.guild_id, count=added)
        return added > 0

    # ---- Idle timeout ------------------------------------------------------

    def _arm_idle_timeout(self) -> None:
        self._cancel_idle_timeout()
        self._idle_task = asyncio.create_task(self._idle_countdown())

    def _cancel_idle_timeout(self) -> None:
        task = self._idle_task
        self._idle_task = None
        if task is None:
            return
        # Nie anuluj samego siebie: _idle_countdown -> teardown -> shutdown ->
        # _cancel_idle_timeout wołane jest Z WNĘTRZA tego taska. cancel() na
        # bieżącym tasku dostarczał CancelledError przy najbliższym await w
        # shutdown(), więc bot po timeoucie zostawał na kanale głosowym.
        if task is asyncio.current_task():
            return
        task.cancel()

    async def _idle_countdown(self) -> None:
        try:
            await asyncio.sleep(self._manager.settings.idle_timeout_seconds)
        except asyncio.CancelledError:
            return
        log.info("idle_timeout", guild_id=self.guild_id)
        await self._manager.teardown(self.guild_id)

    # ---- UI ---------------------------------------------------------------

    def _view(self) -> ControlsView:
        """Jedna instancja ControlsView na gracza, zsynchronizowana ze stanem."""
        from nyxio.ui.controls import ControlsView

        if self._controls_view is None:
            self._controls_view = ControlsView(self)
        self._controls_view.sync()
        return self._controls_view

    async def _publish_now_playing(self, track: Track) -> None:
        from nyxio.ui.embeds import now_playing_embed

        embed = now_playing_embed(
            track,
            self.queue,
            state=self.state,
            volume_pct=self.volume_pct,
            autoplay=self.autoplay,
        )
        try:
            if self.now_playing_message is not None:
                await self.now_playing_message.delete()
        except discord.HTTPException:
            pass
        self.now_playing_message = await self.text_channel.send(
            embed=embed, view=self._view()
        )

    async def refresh_ui(self) -> None:
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
            await self.now_playing_message.edit(embed=embed, view=self._view())
        except discord.NotFound:
            self.now_playing_message = None
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
        # Referencje trzymamy w zbiorze, żeby GC nie ubił taska przed zapisem.
        task = asyncio.create_task(
            self._manager.state_store.save_queue(self.guild_id, self.queue.to_snapshot())
        )
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)

    async def shutdown(self) -> None:
        self._cancel_idle_timeout()
        # Dokoncz w locie zapisy snapshotu do Redis — bez tego graceful restart
        # (clear_state=False, /wznow) potrafi stracic ostatnie zmiany kolejki.
        pending = [t for t in self._persist_tasks if not t.done()]
        if pending:
            try:
                await asyncio.shield(asyncio.gather(*pending, return_exceptions=True))
            except Exception:  # noqa: BLE001
                log.warning("persist_on_shutdown_failed", guild_id=self.guild_id)
        if self._controls_view is not None:
            # Bez stop() widok z timeout=None zostaje w rejestrze discord.py
            # na zawsze — po dobie grania to tysiące żywych obiektów.
            self._controls_view.stop()
            self._controls_view = None
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
