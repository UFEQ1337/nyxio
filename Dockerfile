FROM python:3.12-slim

# Audio transkoduje serwer Lavalink — bot nie potrzebuje FFmpeg ani yt-dlp.
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

# Instalujemy pakiet, tworzymy non-root usera, oddajemy mu /app.
# UID 1000 zeby bind-mount ./data:/app/data dzialal na typowym hoscie.
RUN pip install --no-cache-dir . \
    && useradd -r -u 1000 -m -d /home/nyxio nyxio \
    && mkdir -p /app/data \
    && chown -R nyxio:nyxio /app

USER nyxio

# Tani liveness probe: import paczki = process zyje, modul sie laduje.
# Nie sprawdza polaczenia z Discordem ani Lavalinkiem (te maja wlasne retry).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import nyxio" || exit 1

ENTRYPOINT ["python", "-m", "nyxio"]
