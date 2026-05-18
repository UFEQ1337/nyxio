FROM python:3.12-slim

# Audio transkoduje serwer Lavalink — bot nie potrzebuje FFmpeg ani yt-dlp.
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "nyxio"]
