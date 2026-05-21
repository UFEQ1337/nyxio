#!/bin/sh
set -e

# Bind-mount ./data:/app/data moze nalezec do roota (np. powstal pod starszym
# obrazem, ktory chodzil jako root). Startujemy jako root, naprawiamy wlasciciela
# katalogu danych, a nastepnie zrzucamy uprawnienia na non-root usera 'nyxio'
# i odpalamy wlasciwy proces. Dzieki temu deploy sam sie leczy — bez recznego
# chown na hoscie.
if [ "$(id -u)" = "0" ]; then
    chown -R nyxio:nyxio /app/data 2>/dev/null || true
    exec gosu nyxio "$@"
fi

exec "$@"
