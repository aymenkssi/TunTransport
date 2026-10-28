#!/usr/bin/env bash
# Daily MongoDB backup, keeps 14 days. Cron example (as root, in the deploy folder):
#   0 4 * * * cd /opt/apps/tuntransport/deploy && ./backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
mkdir -p backups
stamp=$(date +%Y-%m-%d_%H%M)
docker compose exec -T mongo mongodump --quiet --archive="/backups/tuntransport-$stamp.gz" --gzip \
  --username "$MONGO_USER" --password "$MONGO_PASSWORD" --authenticationDatabase admin --db tuntransport
find backups -name 'tuntransport-*.gz' -mtime +14 -delete
echo "$(date -Is) backup tuntransport-$stamp.gz OK"
