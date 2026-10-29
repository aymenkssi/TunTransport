#!/usr/bin/env bash
# Optional: self-hosted OSRM for car and walking routes (instead of the public FOSSGIS servers).
# Downloads the Tunisia OpenStreetMap extract and prepares both profiles (≈ 10 min, ~2 GB RAM).
# Then set COMPOSE_PROFILES=osrm and the OSRM_*_URL lines in .env, and run `docker compose up -d`.
# Re-run monthly to refresh the road data.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=ghcr.io/project-osrm/osrm-backend:v5.27.1
mkdir -p osrm/car osrm/foot
curl -fL -o osrm/tunisia.osm.pbf https://download.geofabrik.de/africa/tunisia-latest.osm.pbf
for profile in car foot; do
  cp osrm/tunisia.osm.pbf "osrm/$profile/tunisia.osm.pbf"
  docker run --rm -v "$PWD/osrm/$profile:/data" "$IMAGE" osrm-extract -p "/opt/$profile.lua" /data/tunisia.osm.pbf
  docker run --rm -v "$PWD/osrm/$profile:/data" "$IMAGE" osrm-partition /data/tunisia.osrm
  docker run --rm -v "$PWD/osrm/$profile:/data" "$IMAGE" osrm-customize /data/tunisia.osrm
  rm "osrm/$profile/tunisia.osm.pbf"
done
rm osrm/tunisia.osm.pbf
if docker compose ps --services --status running | grep -q osrm; then docker compose restart osrm-car osrm-foot; fi
echo "$(date -Is) OSRM data ready"
