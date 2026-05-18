"""Buildery embedów: Now Playing (+ pasek postępu), Queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from nyxio.core.queue import LoopMode, TrackQueue
from nyxio.core.track import Track
from nyxio.utils.formatting import format_duration, paginate
from nyxio.utils.progressbar import render_progress

if TYPE_CHECKING:
    from nyxio.core.player import PlayerState

_LOOP_LABEL = {
    LoopMode.NONE: "Wyłączony",
    LoopMode.TRACK: "Utwór 🔂",
    LoopMode.QUEUE: "Kolejka 🔁",
}


def _dur(track: Track) -> str:
    """Długość z ms (wavelink) -> 'M:SS'. Brak/0 = LIVE."""
    return format_duration(track.length // 1000 if track.length else None)


def _total(ms: int) -> str:
    """Łączny czas kolejki -> 'M:SS'. Pusta kolejka -> '—' (nie 'LIVE')."""
    return format_duration(ms // 1000) if ms > 0 else "—"


def _requester(track: Track) -> str:
    if track.requested_by_id:
        return f"<@{track.requested_by_id}>"
    return track.requested_by_name  # np. "AutoPlay"


def now_playing_embed(
    track: Track,
    queue: TrackQueue,
    state: PlayerState | None = None,
    volume_pct: int = 100,
    autoplay: bool = False,
    position_ms: int | None = None,
) -> discord.Embed:
    """Embed 'Teraz odtwarzane'. Gdy podano position_ms (komenda /teraz),
    dodaje pasek postępu odtwarzania."""
    embed = discord.Embed(
        title="🎶 Teraz odtwarzane",
        description=f"### [{track.title}]({track.uri}) `{_dur(track)}`",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🙋 Zamówił", value=_requester(track))
    embed.add_field(name="📺 Kanał", value=track.author or "—")
    embed.add_field(name="🔁 Pętla", value=_LOOP_LABEL[queue.loop_mode])

    if position_ms is not None:
        embed.add_field(
            name="⏱️ Postęp",
            value=f"`{render_progress(position_ms, track.length)}`",
            inline=False,
        )

    total = _total(queue.total_length_ms)
    ap = "🟢 wł." if autoplay else "⚪ wył."
    embed.add_field(
        name="​",
        value=(
            f"▶️ **{len(queue)}** w kolejce · ⏳ {total} grania · "
            f"🔊 {volume_pct}% · 🔀 AutoPlay {ap}"
        ),
        inline=False,
    )
    if state is not None:
        embed.set_footer(text=f"Status: {state.value}")
    if track.artwork:
        embed.set_image(url=track.artwork)
    return embed


def queue_embed(queue: TrackQueue, page: int = 1) -> discord.Embed:
    items, pages = paginate(queue.upcoming, page)
    embed = discord.Embed(title="📜 Kolejka", color=discord.Color.blurple())
    if queue.current is not None:
        embed.add_field(
            name="Teraz",
            value=f"**{queue.current.title}** ({_dur(queue.current)})",
            inline=False,
        )
    if items:
        offset = (page - 1) * 10
        lines = [
            f"`{offset + i + 1}.` {t.title} ({_dur(t)})"
            for i, t in enumerate(items)
        ]
        embed.add_field(name="Następne", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Następne", value="*pusto*", inline=False)
    total = _total(queue.total_length_ms)
    embed.set_footer(text=f"Strona {page}/{pages} · Razem: {len(queue)} · ⏳ {total}")
    return embed


def help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎵 Nyxio — pomoc",
        description="Lista komend. Sterowanie też przyciskami pod *Teraz odtwarzane*.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="▶️ Odtwarzanie",
        value=(
            "`/play <link|fraza>` — dodaj i graj\n"
            "`/teraz` — bieżący utwór + pasek postępu\n"
            "`/pause` — pauza/wznowienie\n"
            "`/skip` — następny · `/previous` — poprzedni\n"
            "`/seek <mm:ss>` — przewiń · `/stop` — zatrzymaj i rozłącz"
        ),
        inline=False,
    )
    embed.add_field(
        name="📜 Kolejka",
        value=(
            "`/queue [str]` — pokaż kolejkę\n"
            "`/loop` — pętla (off/utwór/kolejka)\n"
            "`/shuffle` — przetasuj · `/wznow` — przywróć sesję"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔊 Dźwięk",
        value=(
            "`/volume [0-200]` — głośność\n"
            "`/filter <none|bass|nightcore|eq>` — filtr\n"
            "`/autoplay` — auto-dograj powiązane"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚙️ Ustawienia / inne",
        value="`/dj set|clear|show` — rola DJ · `/ping` — diagnostyka",
        inline=False,
    )
    return embed
