#!/usr/bin/env bash
# Re-imports the lines from tunismapper.com into data/network.json, then reloads them in the API.
# Monthly cron example (as root, in the deploy folder):
#   0 5 1 * * cd /opt/apps/tuntransport/deploy && ./update-network.sh >> data/update.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
python3 ../tools/import_tunismapper.py --out data/network.json --cache data/.cache
docker compose restart api
echo "$(date -Is) network updated"
