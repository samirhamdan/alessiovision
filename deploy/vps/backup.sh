#!/usr/bin/env sh
# Copia de seguranca do banco do Alessio Vision. Guarda os ultimos 14 dias.
# Agendar (todo dia as 3h):  crontab -e  e adicionar a linha
#   0 3 * * * /opt/alessiovision/deploy/vps/backup.sh >> /var/log/alessio-backup.log 2>&1
set -eu
DESTINO=/var/backups/alessio
mkdir -p "$DESTINO"
cd "$(dirname "$0")"
ARQUIVO="$DESTINO/alessio-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T postgres pg_dump -U alessio --clean --if-exists alessio | gzip > "$ARQUIVO"
find "$DESTINO" -name 'alessio-*.sql.gz' -mtime +14 -delete
echo "backup salvo em $ARQUIVO"
