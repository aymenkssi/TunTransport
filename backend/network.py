"""Réseau de transport (lignes, arrêts, tracés, horaires) chargé en mémoire.

Le fichier vient de tools/import_tunismapper.py ; son chemin est NETWORK_FILE.

- GET  /api/lines              : liste des lignes (sans tracés ni horaires).
- GET  /api/lines/{id}         : ligne complète : arrêts, tracé et arrêts de chaque sens, horaires.
- POST /api/lines/suggest      : lignes compatibles avec une trace GPS (pré-remplit le choix du passager).
"""
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from geo import Shape
from matching import GpsFix, match_trace, max_offset_for

logger = logging.getLogger("tuntransport.network")
DEFAULT_FILE = Path(__file__).parent / "data" / "network.json"
SUGGEST_MARGIN_M = 300.0


@dataclass
class LoadedLine:
    data: dict
    shapes: List[Shape]  # un tracé par sens
    max_offset_m: float

    @property
    def id(self) -> str:
        return self.data["id"]

    def summary(self) -> dict:
        keys = ("id", "mode", "short_name", "long_name", "color", "operator")
        return {k: self.data.get(k) for k in keys}


class Network:
    def __init__(self, raw: Optional[dict] = None):
        raw = raw or {"lines": []}
        self.source = raw.get("source")
        self.generated = raw.get("generated")
        self.lines: Dict[str, LoadedLine] = {}
        for line in raw["lines"]:
            shapes = [Shape([tuple(p) for p in d["shape"]]) for d in line["directions"]]
            self.lines[line["id"]] = LoadedLine(line, shapes, max_offset_for(line.get("shape_source")))

    def line(self, line_id: str) -> LoadedLine:
        line = self.lines.get(line_id)
        if line is None:
            raise HTTPException(404, "Unknown line")
        return line


network = Network()


def load(path: Optional[str] = None) -> Network:
    """(Re)charge le réseau ; un fichier absent donne un réseau vide (l'API reste en ligne)."""
    global network
    path = Path(path or os.environ.get("NETWORK_FILE") or DEFAULT_FILE)
    if path.exists():
        network = Network(json.loads(path.read_text(encoding="utf-8")))
        logger.info("Network loaded: %d lines from %s", len(network.lines), path)
    else:
        network = Network()
        logger.warning("Network file %s missing: run tools/import_tunismapper.py", path)
    return network


def current() -> Network:
    return network


# ------------------------ Models ------------------------
class LineSummary(BaseModel):
    id: str
    mode: str
    short_name: str
    long_name: str
    color: Optional[str] = None
    operator: str = ""


class Fix(BaseModel):
    t: float = Field(..., description="secondes depuis l'epoch")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(default=10.0, ge=0, le=10_000)
    mocked: bool = False  # position simulée signalée par le système (Android)

    def to_fix(self) -> GpsFix:
        return GpsFix(self.t, self.lat, self.lon, self.accuracy)


class Trace(BaseModel):
    fixes: List[Fix] = Field(..., min_length=1, max_length=60)


class Suggestion(BaseModel):
    line_id: str
    direction: int
    mean_offset_m: float


# ------------------------ Routes ------------------------
router = APIRouter(prefix="/api")


@router.get("/lines", response_model=List[LineSummary])
async def list_lines():
    return [line.summary() for line in network.lines.values()]


@router.get("/lines/{line_id}")
async def get_line(line_id: str):
    return network.line(line_id).data


@router.post("/lines/suggest", response_model=List[Suggestion])
async def suggest_lines(trace: Trace, limit: int = 3):
    fixes = [f.to_fix() for f in trace.fixes]
    last = max(fixes, key=lambda f: f.t)
    candidates = []
    for line in network.lines.values():
        for direction, shape in enumerate(line.shapes):
            lat_min, lon_min, lat_max, lon_max = shape.bounds(SUGGEST_MARGIN_M)
            if not (lat_min <= last.lat <= lat_max and lon_min <= last.lon <= lon_max):
                continue
            result = match_trace(fixes, shape, line.max_offset_m)
            if result.ok:
                candidates.append(Suggestion(line_id=line.id, direction=direction, mean_offset_m=round(result.mean_offset_m, 1)))
    candidates.sort(key=lambda s: s.mean_offset_m)
    return candidates[: max(1, min(limit, 10))]
