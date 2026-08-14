FROM python:3.12-slim

# Audio transkoduje serwer Lavalink — bot nie potrzebuje FFmpeg ani yt-dlp.
WORKDIR /app

# gosu: zrzucenie uprawnien root -> non-root w entrypoincie (fix bind-mount data).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Instalujemy pakiet, tworzymy non-root usera, oddajemy mu /app.
# UID 1000 zeby bind-mount ./data:/app/data dzialal na typowym hoscie.
RUN pip install --no-cache-dir . \
    && useradd -r -u 1000 -m -d /home/nyxio nyxio \
    && mkdir -p /app/data \
    && chown -R nyxio:nyxio /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Liveness probe czyta heartbeat pisany przez zywy proces bota (bot.py:
# HEARTBEAT_PATH). Poprzednia wersja robila `import nyxio` w NOWYM procesie —
# przechodzila nawet wtedy, gdy bot wisial rozlaczony od Discorda.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,sys,time; p='/tmp/nyxio.healthy'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 90 else 1)"

# Entrypoint startuje jako root, naprawia wlasciciela /app/data, po czym
# dropuje do usera 'nyxio' (gosu) i odpala CMD. Brak USER w Dockerfile jest
# celowy — drop uprawnien robi entrypoint, a bot dziala jako non-root.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "nyxio"]
