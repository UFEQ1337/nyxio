"""pot-refresher — utrzymuje świeży poToken/visitorData w Lavalinku.

Dlaczego to osobny serwis, a nie wpis w application.yml:

Plugin youtube-source czyta `plugins.youtube.pot.token` i `.visitorData` TYLKO
przy starcie, a para wygasa po kilku–kilkunastu godzinach. Ręczne wklejanie do
.env i restart Lavalinka co dobę to nie jest deploy, który się utrzyma.

Plugin wystawia jednak REST-owy endpoint `POST /youtube` przyjmujący
{refreshToken, poToken, visitorData, skipInitialization} i podmieniający je
**na żywo, bez restartu** (dev/lavalink/youtube/plugin/YoutubeRestHandler:
"Updated poToken to {} and visitorData to {}"). Ten serwis w pętli generuje
nową parę i wysyła ją tym endpointem.

Konfiguracja (zmienne środowiskowe):
  LAVALINK_URL            domyślnie http://lavalink:2333
  LAVALINK_PASSWORD       hasło do REST API Lavalinka (wymagane)
  POT_REFRESH_HOURS       co ile odświeżać parę (domyślnie 6)
  POT_GENERATOR_CMD       polecenie generatora; jego stdout jest parsowany
  POT_TOKEN / POT_VISITOR_DATA
                          para statyczna — używana zamiast generatora, gdy
                          ustawiona. Przydatna, gdy wolisz generować ręcznie:
                          serwis i tak dopilnuje, żeby Lavalink ją miał po
                          każdym swoim restarcie.
  YOUTUBE_REFRESH_TOKEN   opcjonalnie dosyłany razem z parą (OAuth).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Generator drukuje parę na stdout. Formaty bywają różne między wersjami
# obrazu, więc akceptujemy zarówno "klucz: wartość", jak i JSON-a.
_VISITOR_KEYS = ("visitor_data", "visitordata", "visitor")
_TOKEN_KEYS = ("po_token", "potoken", "token")
_LINE_RE = re.compile(r"^\s*([A-Za-z_]+)\s*[:=]\s*(\S+)\s*$")


def _log(event: str, **fields: object) -> None:
    """Log w tym samym formacie co reszta stacku (JSON, jedna linia)."""
    payload = {"event": event, "service": "pot-refresher", **fields}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def parse_pot(text: str) -> tuple[str, str] | None:
    """Wyciąga (visitorData, poToken) ze stdoutu generatora.

    Zwraca None, gdy brakuje którejkolwiek połowy pary — niesparowane wartości
    są gorsze niż ich brak (YouTube odpowiada wtedy "Video player configuration
    error", co trudno powiązać z przyczyną).
    """
    visitor: str | None = None
    token: str | None = None

    # 1. Próba JSON-a (cały tekst albo pojedyncza linia).
    for candidate in (text, *text.splitlines()):
        candidate = candidate.strip()
        if not candidate.startswith("{"):
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            norm = key.lower().replace("-", "_")
            if not isinstance(value, str) or not value:
                continue
            if norm in _VISITOR_KEYS:
                visitor = value
            elif norm in _TOKEN_KEYS:
                token = value
        if visitor and token:
            return visitor, token

    # 2. Format "klucz: wartość" linia po linii.
    for line in text.splitlines():
        match = _LINE_RE.match(line)
        if match is None:
            continue
        norm = match.group(1).lower()
        if norm in _VISITOR_KEYS:
            visitor = match.group(2)
        elif norm in _TOKEN_KEYS:
            token = match.group(2)

    if visitor and token:
        return visitor, token
    return None


def generate() -> tuple[str, str] | None:
    """Uruchamia generator i zwraca parę. None = nie udało się."""
    static_token = os.environ.get("POT_TOKEN", "").strip()
    static_visitor = os.environ.get("POT_VISITOR_DATA", "").strip()
    if static_token and static_visitor:
        return static_visitor, static_token

    cmd = os.environ.get("POT_GENERATOR_CMD", "").strip()
    if not cmd:
        _log("generator_not_configured")
        return None

    try:
        proc = subprocess.run(  # noqa: S602 - polecenie pochodzi z konfiguracji operatora
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        _log("generator_timeout", cmd=cmd)
        return None
    except OSError as exc:
        _log("generator_spawn_failed", cmd=cmd, error=str(exc))
        return None

    combined = f"{proc.stdout}\n{proc.stderr}"
    pair = parse_pot(combined)
    if pair is None:
        # Najczęstsza przyczyna: obraz generatora zmienił ścieżkę/entrypoint.
        # Wypisujemy ogon wyjścia, żeby dało się to poprawić bez zgadywania.
        _log(
            "generator_output_unparsed",
            cmd=cmd,
            returncode=proc.returncode,
            tail=combined.strip()[-400:],
            hint="ustaw POT_GENERATOR_CMD na polecenie drukujące visitor_data i po_token",
        )
    return pair


def push(visitor: str, token: str) -> bool:
    """Wysyła parę do Lavalinka (POST /youtube). True = przyjęte."""
    base = os.environ.get("LAVALINK_URL", "http://lavalink:2333").rstrip("/")
    password = os.environ.get("LAVALINK_PASSWORD", "")
    # NIE wysyłamy tu refreshTokena. Lavalink loguje cale cialo zadania POST
    # (RequestLoggingFilter), wiec kazdy push ladowal token OAuth w plaintekscie
    # do logow kontenera. Token i tak trafia do pluginu ze zmiennej srodowiskowej
    # przy starcie — dosylanie go nic nie wnosilo, a wynosilo sekret.
    # (poToken/visitorData tez sa logowane, dlatego w application.yml wylaczamy
    #  includePayload dla logu zadan.)
    body: dict[str, object] = {"poToken": token, "visitorData": visitor}

    request = urllib.request.Request(
        f"{base}/youtube",
        data=json.dumps(body).encode(),
        headers={"Authorization": password, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            ok = 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        _log("push_http_error", status=exc.code, reason=exc.reason)
        return False
    except OSError as exc:
        _log("push_failed", error=str(exc))
        return False
    if ok:
        # Same tokeny nie trafiają do logów — to sekrety.
        _log("pot_updated", visitor_len=len(visitor), token_len=len(token))
    return ok


def main() -> int:
    if not os.environ.get("LAVALINK_PASSWORD"):
        _log("missing_lavalink_password")
        return 1

    interval_h = float(os.environ.get("POT_REFRESH_HOURS", "6"))
    interval_s = max(60.0, interval_h * 3600.0)
    # Lavalink potrzebuje chwili na wstanie JVM i rejestrację pluginu.
    time.sleep(float(os.environ.get("POT_STARTUP_DELAY_S", "45")))

    while True:
        pair = generate()
        if pair is None:
            # Krótszy backoff — nie chcemy czekać pełnych 6h na kolejną próbę.
            _log("refresh_skipped", retry_in_s=600)
            time.sleep(600)
            continue
        if not push(*pair):
            _log("refresh_retry", retry_in_s=600)
            time.sleep(600)
            continue
        time.sleep(interval_s)


if __name__ == "__main__":
    sys.exit(main())
