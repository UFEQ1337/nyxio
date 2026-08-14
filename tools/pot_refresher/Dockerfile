# pot-refresher — utrzymuje swiezy poToken/visitorData w Lavalinku przez REST
# (POST /youtube), bez restartu Lavalinka.
#
# Domyslnie budujemy na czystym Pythonie: sam refresher potrzebuje wylacznie
# biblioteki standardowej. W tym trybie serwis dziala jako "dosylacz" — bierze
# pare z POT_TOKEN/POT_VISITOR_DATA i pilnuje, zeby Lavalink mial ja po kazdym
# swoim restarcie i po wygasnieciu wpisu w pamieci pluginu.
#
# Tryb automatyczny (generowanie pary w kontenerze) wlaczasz podmieniajac obraz
# bazowy na obraz generatora i podajac polecenie, ktore drukuje pare:
#   NYXIO_POT_BASE_IMAGE=quay.io/invidious/youtube-trusted-session-generator
#   NYXIO_POT_GENERATOR_CMD=<polecenie drukujace visitor_data i po_token>
# Uwaga: generatory oparte na headless chromium bywaja za ciezkie dla malych
# instancji ARM (na tym VPS-ie timeoutowaly) — dlatego NIE sa domyslne.
ARG POT_BASE_IMAGE=python:3.12-slim
FROM ${POT_BASE_IMAGE}

COPY refresher.py /usr/local/bin/refresher.py

# Czyscimy entrypoint obrazu bazowego — przy obrazie generatora jego wlasny
# entrypoint odpalilby generator zamiast naszej petli.
ENTRYPOINT []
CMD ["python", "-u", "/usr/local/bin/refresher.py"]
