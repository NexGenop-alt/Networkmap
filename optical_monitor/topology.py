from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = ROOT / "topology.json"


@lru_cache(maxsize=1)
def load_topology() -> dict[str, Any]:
    with TOPOLOGY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def node_ports() -> dict[str, list[str]]:
    ports: dict[str, set[str]] = {}
    for node in load_topology()["nodes"]:
        if node.get("type") != "cloud":
            ports[node["id"]] = set()

    for link in load_topology()["links"]:
        link_ports = link.get("ports") or {}
        for end, node_key in (("from", "from"), ("to", "to")):
            node_id = link.get(node_key)
            raw = str(link_ports.get(end) or "")
            extracted = _extract_ports(raw)
            if node_id in ports:
                ports[node_id].update(extracted)

    for node_id, values in ports.items():
        if not values:
            values.add("35")
        ports[node_id] = values
    return {node_id: sorted(values) for node_id, values in ports.items()}


def _extract_ports(raw: str) -> list[str]:
    values: list[str] = []
    for token in raw.replace(",", " ").split():
        cleaned = token.strip()
        if not cleaned or cleaned.startswith("."):
            continue
        if any(char.isdigit() for char in cleaned) and ("p" in cleaned.lower() or cleaned.isdigit()):
            values.append(cleaned.removeprefix("p"))
    return values

