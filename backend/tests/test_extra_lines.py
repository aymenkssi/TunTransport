import json
from pathlib import Path

import network

BUILT = Path(__file__).resolve().parents[2] / "tools/extra_lines.built.json"


def test_extra_lines_load_and_serve_stops_in_order():
    lines = json.loads(BUILT.read_text(encoding="utf-8"))["lines"]
    net = network.Network({"source": "test", "generated": "2026-10-31", "lines": lines})
    for line in lines:
        loaded = net.line(line["id"])
        stop_ids = {s["id"] for s in line["stops"]}
        for direction, shape in zip(line["directions"], loaded.shapes):
            alongs = [s["along_m"] for s in direction["stops"]]
            assert alongs == sorted(alongs) and alongs[-1] <= shape.length_m + 1
            assert {s["id"] for s in direction["stops"]} == stop_ids
