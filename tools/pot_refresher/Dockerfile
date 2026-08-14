# pot-refresher — generuje parę poToken/visitorData i wpycha ją do Lavalinka
# przez REST (POST /youtube), bez restartu Lavalinka.
#
# Bazujemy na obrazie generatora, bo to on ciągnie headless Chromium i całą
# logikę wyciągania tokena; my dokładamy tylko pętlę i klienta REST.
# Obraz bazowy podmienisz argumentem build:
#   docker compose build --build-arg POT_BASE_IMAGE=<inny-obraz> pot-refresher
ARG POT_BASE_IMAGE=ghcr.io/iv-org/youtube-trusted-session-generator:latest
FROM ${POT_BASE_IMAGE}

COPY refresher.py /usr/local/bin/refresher.py

# Nadpisujemy entrypoint obrazu bazowego — generator odpalamy sami, w pętli,
# poleceniem z POT_GENERATOR_CMD (patrz docker-compose.yml).
ENTRYPOINT []
CMD ["python", "-u", "/usr/local/bin/refresher.py"]
