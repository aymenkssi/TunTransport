#!/usr/bin/env bash
# Re-imports the lines from tunismapper.com (data/network.json) and the Grand Tunis addresses from
# OpenStreetMap (data/places.json), then reloads them in the API.
# Monthly cron example (as root, in the deploy folder):
#   0 5 1 * * cd /opt/apps/tuntransport/deploy && ./update-network.sh >> data/update.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
python3 ../tools/import_tunismapper.py --out data/network.json --cache data/.cache
# Overpass is sometimes overloaded: keep the previous address index rather than failing the update.
python3 ../tools/import_places.py --out data/places.json || echo "$(date -Is) address import failed, previous index kept"
docker compose restart api
echo "$(date -Is) network updated"
