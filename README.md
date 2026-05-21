# Nyxio 🎶

> Autor: **[UFEQ1337](https://github.com/UFEQ1337)** · Licencja: **MIT** ·
> © 2026 UFEQ1337

Nowoczesny bot muzyczny dla Discorda: odtwarzanie z YouTube, kolejka z
historią, filtry audio, przewijanie, AutoPlay i interaktywny interfejs
(embed „Teraz odtwarzane” + przyciski). Slash-only, polski UI.

Stworzone przez **UFEQ1337**. Możesz używać za darmo — wymagane
zachowanie informacji o autorze (patrz [Licencja](#licencja)).

**Stos:** Python 3.12 · discord.py 2.7 · wavelink 3 · **Lavalink v4**
(wtyczka `youtube-source`) · Redis · Docker Compose.

---

## Architektura

Cztery kontenery (`docker-compose.yml`):

| Usługa | Rola |
|---|---|
| **bot** | Logika: komendy, kolejka, UI, stan per-serwer (Python, lekki ~50 MB RAM) |
| **lavalink** | Pozyskiwanie i **transkodowanie audio** (JVM); bot sam nie koduje dźwięku |
| **yt-cipher** | Zdalny deszyfrator sygnatur YouTube — odciąża wtyczkę `youtube-source` przy nowych wersjach player-script |
| **redis** | Trwały snapshot kolejki → wznowienie sesji po restarcie (`/wznow`) |

Zależności startowe: `yt-cipher` → `lavalink` (healthcheck) → `bot`.

### Dlaczego Lavalink, a nie yt-dlp/FFmpeg?

Wcześniej rozważany silnik natywny (yt-dlp + FFmpeg w procesie bota)
został **zastąpiony przez Lavalink**. Powody:

- **Brak transkodowania w bocie** — CPU obciąża serwer Lavalink, nie
  proces Pythona. Skaluje się liniowo niezależnie od bota.
- **Stabilniejsze źródła** — wtyczka `youtube-source` zamiast kruchego
  `yt-dlp` (mniej „psucia się” przy zmianach YouTube).
- **Filtry i seek za darmo** — equalizer / bass / nightcore oraz
  przewijanie w utworze obsługuje Lavalink natywnie.

> `yt-dlp` ani `FFmpeg` **nie są używane** i nie ma ich w obrazie bota.
> Rozwiązywanie linków/fraz robi `wavelink.Playable.search` → Lavalink.

### Po co osobny `yt-cipher`?

Lokalny parser sygnatur we wtyczce `youtube-source` bywa nieaktualny przy
najświeższych wersjach player-script YouTube (błąd *„must find sig
function”*). Kontener `yt-cipher` liczy sygnaturę po stronie serwera i
nie wystawia portu na hosta — Lavalink łączy się z nim wyłącznie po
wewnętrznej sieci Compose. Współdzielony sekret (`NYXIO_YTCIPHER_TOKEN`)
zabezpiecza ten endpoint.

### Model działania

`GuildPlayer` (per serwer) jest **sterowany zdarzeniami** wavelink
(`on_wavelink_track_end` → następny utwór) — brak wątków FFmpeg i pętli
blokujących. `TrackQueue` to czysta logika (kolejność, historia →
`/previous`, tryby pętli, shuffle) — w pełni testowalna bez sieci.
Błędy są izolowane per-serwer.

---

## Szybki start (Docker)

```bash
cp .env.example .env          # ustaw NYXIO_DISCORD_TOKEN i NYXIO_YTCIPHER_TOKEN
mkdir -p data && sudo chown 1000:1000 data   # kontener bota chodzi jako uid 1000
docker compose up -d --build
docker compose logs -f bot    # czekaj na "lavalink_node_ready" i "ready"
```

> Bot dziala wewnatrz kontenera jako non-root user (uid 1000). Bind-mount
> `./data:/app/data` musi miec wlasciciela 1000, inaczej zapis `guild_config.json`
> rzuci `Permission denied`. Na Windows/WSL `chown` mozna pominac (Docker Desktop
> robi mapowanie automatycznie); na Linux/VPS trzeba ustawic recznie raz.

Lavalink (JVM) startuje ~20–40 s; bot czeka na jego `healthcheck`
(`depends_on: service_healthy`) i dodatkowo ponawia połączenie węzła.

## Uruchomienie lokalne (bez Dockera)

Wymaga **działającego węzła Lavalink v4** z wtyczką `youtube-source`
(konfiguracja: [`lavalink/application.yml`](lavalink/application.yml)).

```bash
python -m venv .venv && .venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m nyxio
```

`NYXIO_DEV_GUILD_ID` ustawione → slash-komendy synchronizują się
natychmiast w jednej gildii; puste → globalnie (do ~1 h propagacji).

---

## Komendy

**Odtwarzanie**

| Komenda | Opis |
|---|---|
| `/play <link\|fraza>` | Dodaj utwór/playlistę i graj (YouTube) |
| `/playnext <link\|fraza>` | Dodaj na początek kolejki (zagra zaraz po bieżącym) |
| `/teraz` | Bieżący utwór + pasek postępu |
| `/pause` | Pauza / wznowienie |
| `/skip` · `/previous` | Następny / poprzedni (z historii) |
| `/seek <mm:ss>` | Przewiń w utworze |
| `/stop` | Zatrzymaj i rozłącz |

**Kolejka**

| Komenda | Opis |
|---|---|
| `/queue [strona]` | Pokaż kolejkę |
| `/loop` | Pętla: off → utwór → kolejka |
| `/shuffle` | Przetasuj |
| `/wznow` | Przywróć kolejkę z poprzedniej sesji (z Redis) |

**Dźwięk**

| Komenda | Opis |
|---|---|
| `/volume [0-200]` | Głośność (trwała per-serwer) |
| `/filter <none\|bass\|nightcore\|eq>` | Filtr audio |
| `/autoplay` | Auto-dograj powiązane gdy kolejka pusta |

**Inne:** `/pomoc` (lista komend) · `/dj set\|clear\|show` (rola DJ) ·
`/ping` (diagnostyka) · `/resync` (resynchronizacja — właściciel bota).

Pod embedem *Teraz odtwarzane* są przyciski (3 rzędy): Poprzedni ·
Pauza · Następny · Stop · Pętla / Ciszej · Głośniej · Losuj · Kolejka ·
Teraz / AutoPlay. Działają tylko dla osób na tym samym kanale głosowym.

---

## Zaproszenie na serwer

Developer Portal → **OAuth2 → URL Generator** → scopes `bot` +
`applications.commands`, uprawnienia: *View Channels*, *Send Messages*,
*Embed Links*, *Connect*, *Speak*:

```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=3214336&scope=bot%20applications.commands
```

Intencja: tylko `voice_states` (nieprzywilejowana). **Żadne przywileje**
(Message Content / Members / Presence) **nie są wymagane** — bot jest
slash-only, audio leci przez Lavalink (PyNaCl/davey niepotrzebne).

## Uprawnienia (rola DJ)

Konfigurowane komendą, per serwer, w trakcie działania (trwałe w
`data/guild_config.json`):

| Komenda | Opis |
|---|---|
| `/dj set @Rola` | Tylko ta rola + administratorzy sterują muzyką |
| `/dj clear` | Dostęp dla każdego |
| `/dj show` | Pokaż aktualną rolę |

`/dj *` wymaga *Zarządzania serwerem* (egzekwowane w kodzie i natywnie
przez *Integracje* Discorda). Brak roli = dostęp dla każdego;
administrator ma dostęp zawsze.
Logika: [`utils/permissions.py`](src/nyxio/utils/permissions.py).

---

## Konfiguracja (`.env`, prefiks `NYXIO_`)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `NYXIO_DISCORD_TOKEN` | — | Token bota (wymagane) |
| `NYXIO_DEV_GUILD_ID` | — | ID gildii do natychmiastowego sync (dev) |
| `NYXIO_MAX_QUEUE_SIZE` | 500 | Limit kolejki |
| `NYXIO_MAX_PLAYLIST_ITEMS` | 100 | Limit pozycji z playlisty |
| `NYXIO_IDLE_TIMEOUT_SECONDS` | 180 | Auto-rozłączenie po bezczynności |
| `NYXIO_REDIS_URL` | — | np. `redis://redis:6379/0` (snapshot/wznów) |
| `NYXIO_LAVALINK_HOST` | `lavalink` | Host węzła Lavalink |
| `NYXIO_LAVALINK_PORT` | `2333` | Port węzła |
| `NYXIO_LAVALINK_PASSWORD` | `youshallnotpass` | Hasło węzła |

Zmienne czytane przez `docker-compose.yml` (Lavalink / YouTube):

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `NYXIO_YTCIPHER_TOKEN` | `changeme` | Sekret współdzielony Lavalink ↔ `yt-cipher` (ustaw własny) |
| `NYXIO_YOUTUBE_REFRESH_TOKEN` | — | OAuth YouTube — omija „This video requires login” na VPS (zob. niżej) |
| `NYXIO_PO_TOKEN` / `NYXIO_VISITOR_DATA` | — | Opcjonalny poToken; zwykle zbędny gdy działa `yt-cipher` + OAuth |

Wzór: [`.env.example`](.env.example). `.env` i `data/` są w
`.gitignore` — sekrety nigdy nie trafiają do repo.

### Trwałość

- **`data/guild_config.json`** (wolumen Docker) — rola DJ, domyślna
  głośność, AutoPlay. Przeżywa restart/przebudowę kontenera.
- **Redis** — snapshot kolejki per serwer; `/wznow` odtwarza sesję po
  restarcie (re-resolve przez Lavalink). Odtwarzanie **nie** wznawia
  się automatycznie (świadoma decyzja).

---

## Wdrożenie na VPS

```bash
git clone https://github.com/UFEQ1337/nyxio.git && cd nyxio
cp .env.example .env && nano .env     # token + hasło Lavalink
chmod 600 .env
docker compose up -d --build
```

Obrazy są multi-arch (x86_64 i ARM64 — np. Oracle/Ampere działa).
Zalecane ≥ 2 GB RAM (Lavalink JVM `-Xmx1g` + narzut). Aktualizacja:
`git pull && docker compose up -d --build`.

> **Pierwszy start na VPS:** YouTube często wymaga logowania spoza
> domowego IP. Zostaw `NYXIO_YOUTUBE_REFRESH_TOKEN` puste — Lavalink
> wypisze w logach link i kod do autoryzacji (zaloguj konto *burner*).
> Wklej zwrócony `refreshToken` do `.env` i zrestartuj. Szczegóły w
> komentarzach [`.env.example`](.env.example).

## Jakość

```bash
ruff check . && mypy src/ && pytest
```

`ruff` (lint) · `mypy --strict` · **pytest** (logika kolejki, restore,
filtry, parsowanie zapytań, pasek postępu, FSM playera — bez sieci).

## Struktura

```
src/nyxio/
├── bot.py            # NyxioBot: setup_hook, Pool.connect, zdarzenia wavelink
├── config.py         # pydantic-settings (NYXIO_*)
├── cogs/             # music · admin · settings (komendy slash)
├── core/             # player (GuildPlayer) · queue · track · manager
│                     #   · guild_config · restore
├── ui/               # embeds (Now Playing/pomoc) · controls (przyciski)
├── infra/            # logging · state_store (Redis) · supervisor
└── utils/            # query · filters · progressbar · permissions · ...
lavalink/application.yml   # konfiguracja węzła + wtyczka youtube-source
docker-compose.yml         # bot + lavalink + yt-cipher + redis
```

---

## Autor

**UFEQ1337** — [github.com/UFEQ1337](https://github.com/UFEQ1337)

Projekt zaprojektowany i zaimplementowany przez UFEQ1337.

## Licencja

Wydane na licencji **MIT** — pełny tekst w pliku [`LICENSE`](LICENSE).

Możesz **bezpłatnie** używać, kopiować, modyfikować, rozpowszechniać i
wykorzystywać komercyjnie ten projekt — pod jednym warunkiem:
**zachowujesz informację o prawach autorskich i treść licencji**
(uznanie autorstwa: © 2026 UFEQ1337). Oprogramowanie dostarczane „as
is”, bez gwarancji.

