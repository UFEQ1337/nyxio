# Nyxio 🎶

Nowoczesny bot muzyczny dla Discorda: odtwarzanie z YouTube, kolejkowanie,
kontrola transportu i interaktywny UI (przyciski Discord).

Stos: **Python 3.12 · discord.py 2.x · yt-dlp · FFmpeg** · opcjonalnie Redis.
Architektura: per-gildia maszyna stanów + nadzorowane taski, izolacja błędów,
streaming bez zapisu na dysk. Pełny dokument projektowy: zob. plan SDD.

## Szybki start (Docker)

```bash
cp .env.example .env          # uzupełnij NYXIO_DISCORD_TOKEN
docker compose up --build
```

## Uruchomienie lokalne

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
# wymagany FFmpeg w PATH
python -m nyxio
```

Ustaw `NYXIO_DEV_GUILD_ID` na czas developmentu — slash-komendy
synchronizują się wtedy natychmiast w jednej gildii.

## Komendy

| Komenda | Opis |
|---|---|
| `/play <link\|fraza>` | Dodaj utwór/playlistę i odtwórz |
| `/skip` | Pomiń bieżący utwór |
| `/pause` | Pauza / wznowienie |
| `/stop` | Zatrzymaj i rozłącz |
| `/queue [strona]` | Pokaż kolejkę |
| `/loop` | Pętla: off → utwór → kolejka |
| `/shuffle` | Przetasuj kolejkę |
| `/ping` | Diagnostyka |

Pod embedem *Teraz odtwarzane* dostępne są przyciski: ⏯️ ⏭️ 🔁 📜 ⏹️
(tylko dla osób na tym samym kanale głosowym).

## Zaproszenie na serwer

Developer Portal → **OAuth2 → URL Generator** → scopes `bot` +
`applications.commands`, uprawnienia: *View Channels*, *Send Messages*,
*Embed Links*, *Connect*, *Speak*. Otwórz wygenerowany URL i wybierz serwer:

```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=3214336&scope=bot%20applications.commands
```

Intencje: tylko `voice_states` (nieprzywilejowana). **Żadne przywileje
w Developer Portal nie są wymagane** — nie trzeba włączać Message
Content / Members / Presence. Resynchronizacja komend: `/resync`
(tylko właściciel bota).

## Kto może używać komend

Rolę DJ ustawia się **komendą, per serwer, w trakcie działania** —
ustawienie jest trwale zapisywane (`data/guild_config.json`):

| Komenda | Opis |
|---|---|
| `/dj set @Rola` | Tylko ta rola + administratorzy sterują muzyką |
| `/dj clear` | Dostęp dla każdego |
| `/dj show` | Pokaż aktualną rolę DJ |

`/dj *` wymaga uprawnienia *Zarządzanie serwerem* (egzekwowane w kodzie
oraz natywnie — *Ustawienia serwera → Integracje → Nyxio*).

Brak ustawionej roli DJ = dostęp dla każdego. Administrator serwera ma
dostęp zawsze. Logika:
[`utils/permissions.py`](src/nyxio/utils/permissions.py),
[`core/guild_config.py`](src/nyxio/core/guild_config.py).

## Jakość

```bash
ruff check . && mypy src/ && pytest
```

## Konfiguracja (zmienne `NYXIO_*`)

Patrz [`.env.example`](.env.example): limity kolejki/playlisty,
współbieżność ekstrakcji, idle-timeout, bitrate, `REDIS_URL`.
