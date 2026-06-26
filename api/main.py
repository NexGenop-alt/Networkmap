from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from optical_monitor.db import connect, init_db
from optical_monitor.topology import load_topology


app = FastAPI(title="Wyyerd Optical Monitor API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/topology")
def topology() -> dict[str, Any]:
    return load_topology()


@app.get("/api/nodes")
def nodes(at: Optional[str] = None) -> list[dict[str, Any]]:
    topo = load_topology()
    latest = latest_aggregates(at)
    
    active_ports: dict[str, set[str]] = {}
    for link in topo["links"]:
        for direction in ["from", "to"]:
            node_id = link[direction]
            port_str = link.get("ports", {}).get(direction, "")
            # Default split() handles your spaces perfectly!
            for token in port_str.split():
                clean_port = token.strip().replace("p", "")
                if clean_port:
                    active_ports.setdefault(node_id, set()).add(clean_port)

    result = []
    for node in topo["nodes"]:
        node_id = node["id"]
        allowed_ports = active_ports.get(node_id, set())
        
        all_node_readings = list(latest.get(node_id, {}).values())
        filtered_ports = [
            r for r in all_node_readings 
            if str(r["port"]).replace("p", "") in allowed_ports
        ]
        
        result.append(node | {
            "ports": filtered_ports,
            "health": node_health(filtered_ports),
        })
    return result


@app.get("/api/nodes/{node_id}")
def node_detail(node_id: str, at: Optional[str] = None) -> dict[str, Any]:
    topo = load_topology()
    node = next((item for item in topo["nodes"] if item["id"] == node_id), None)
    
    allowed_ports = set()
    for link in topo["links"]:
        if link["from"] == node_id:
            for token in link.get("ports", {}).get("from", "").split():
                allowed_ports.add(token.strip().replace("p", ""))
        elif link["to"] == node_id:
            for token in link.get("ports", {}).get("to", "").split():
                allowed_ports.add(token.strip().replace("p", ""))
                
    ports_map = latest_aggregates(at).get(node_id, {})
    lanes = latest_lanes(node_id, at)
    
    filtered_ports = [
        port for port in ports_map.values()
        if str(port["port"]).replace("p", "") in allowed_ports
    ]
    
    return {
        "node": node,
        "ports": [
            port | {"lanes": lanes.get(port["port"], [])}
            for port in filtered_ports
        ],
    }

@app.get("/api/nodes/{node_id}/history")
def node_history(node_id: str, hours: int = 24) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, port, rx_dbm, tx_dbm, in_crc_errors, out_discards
            FROM optical_readings
            WHERE node_id = ? AND lane IS NULL AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (node_id, since),
        ).fetchall()
    series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        series.setdefault(row["port"], []).append(dict(row))
    return {"node_id": node_id, "hours": hours, "series": series}


@app.get("/api/links")
def links(at: Optional[str] = None) -> list[dict[str, Any]]:
    topo = load_topology()
    latest = latest_aggregates(at)
    return [enrich_link(link, latest) for link in topo["links"]]


@app.get("/api/links/{link_id}")
def link_detail(link_id: str, at: Optional[str] = None) -> dict[str, Any]:
    topo = load_topology()
    latest = latest_aggregates(at)
    link = next((item for item in topo["links"] if item["id"] == link_id), None)
    return enrich_link(link, latest) if link else {"error": "link not found"}


@app.get("/api/health")
def health(at: Optional[str] = None) -> dict[str, Any]:
    link_health = Counter(link["health"] for link in links(at))
    at_filter = normalize_at(at)
    with connect() as conn:
        status = conn.execute("SELECT * FROM collector_status WHERE id = 1").fetchone()
        if at_filter:
            newest = conn.execute(
                "SELECT MAX(timestamp) AS timestamp FROM optical_readings WHERE timestamp <= ?",
                (at_filter,),
            ).fetchone()
        else:
            newest = conn.execute("SELECT MAX(timestamp) AS timestamp FROM optical_readings").fetchone()
    return {
        "ok": True,
        "as_of": at_filter,
        "collector": dict(status) if status else None,
        "latest_reading_at": newest["timestamp"] if newest else None,
        "summary": {
            "nodes": len(load_topology()["nodes"]),
            "links": len(load_topology()["links"]),
            "healthy": link_health["healthy"],
            "warning": link_health["warning"],
            "critical": link_health["critical"],
            "unknown": link_health["unknown"],
        },
    }


@app.websocket("/api/ws/live")
async def live(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"health": health(), "links": links()})
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        return


def normalize_at(at: Optional[str]) -> Optional[str]:
    if not at:
        return None
    try:
        value = at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return None


def latest_aggregates(at: Optional[str] = None) -> dict[str, dict[str, dict[str, Any]]]:
    at_filter = normalize_at(at)
    time_clause = "AND timestamp <= ?" if at_filter else ""
    params = (at_filter,) if at_filter else ()
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*
            FROM optical_readings r
            JOIN (
                SELECT node_id, port, MAX(timestamp) AS timestamp
                FROM optical_readings
                WHERE lane IS NULL
                {time_clause}
                GROUP BY node_id, port
            ) latest
            ON r.node_id = latest.node_id
                AND r.port = latest.port
                AND r.timestamp = latest.timestamp
            WHERE r.lane IS NULL
            """,
            params,
        ).fetchall()
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        item["health"] = reading_health(item)
        item.pop("raw_json", None)
        grouped.setdefault(item["node_id"], {})[item["port"]] = item
    return grouped


def latest_lanes(node_id: str, at: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    at_filter = normalize_at(at)
    time_clause = "AND timestamp <= ?" if at_filter else ""
    params = (node_id, at_filter, node_id) if at_filter else (node_id, node_id)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*
            FROM optical_readings r
            JOIN (
                SELECT node_id, port, lane, MAX(timestamp) AS timestamp
                FROM optical_readings
                WHERE node_id = ? AND lane IS NOT NULL
                {time_clause}
                GROUP BY node_id, port, lane
            ) latest
            ON r.node_id = latest.node_id
                AND r.port = latest.port
                AND r.lane = latest.lane
                AND r.timestamp = latest.timestamp
            WHERE r.node_id = ? AND r.lane IS NOT NULL
            ORDER BY r.port, r.lane
            """,
            params,
        ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        item["health"] = reading_health(item)
        item.pop("raw_json", None)
        grouped.setdefault(item["port"], []).append(item)
    return grouped


def enrich_link(link: dict[str, Any], latest: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    if not link:
        return {"error": "link not found"}
    endpoints = [
        best_endpoint_reading(latest.get(link["from"], {}), (link.get("ports") or {}).get("from")),
        best_endpoint_reading(latest.get(link["to"], {}), (link.get("ports") or {}).get("to")),
    ]
    readings = [item for item in endpoints if item]
    worst = worst_health([item["health"] for item in readings])
    if not readings:
        worst = "unknown"
    return link | {
        "endpoints": endpoints,
        "health": worst,
        "rx_dbm": round(sum(item["rx_dbm"] for item in readings if item.get("rx_dbm") is not None) / len(readings), 2)
        if readings else None,
        "tx_dbm": round(sum(item["tx_dbm"] for item in readings if item.get("tx_dbm") is not None) / len(readings), 2)
        if readings else None,
        "last_updated": max((item["timestamp"] for item in readings), default=None),
        "issues": sum((item.get("in_crc_errors") or 0) + (item.get("out_discards") or 0) for item in readings),
    }


def best_endpoint_reading(port_map: dict[str, dict[str, Any]], port_hint: str | None) -> dict[str, Any] | None:
    if not port_map:
        return None
    if port_hint:
        hint = str(port_hint)
        for port, reading in port_map.items():
            if port in hint or f"p{port}" in hint:
                return reading
    return next(iter(port_map.values()))


def reading_health(row: dict[str, Any]) -> str:
    rx = row.get("rx_dbm")
    if rx is None:
        return "unknown"
    low_alarm = row.get("rx_low_alarm")
    low_warning = row.get("rx_low_warning")
    if low_alarm is not None and rx <= low_alarm:
        return "critical"
    if low_warning is not None and rx <= low_warning:
        return "warning"
    if (row.get("in_crc_errors") or 0) > 0 or (row.get("out_discards") or 0) > 0:
        return "warning"
    return "healthy"


def node_health(ports: list[dict[str, Any]]) -> str:
    return worst_health([port["health"] for port in ports]) if ports else "unknown"


def worst_health(statuses: list[str]) -> str:
    rank = {"unknown": 0, "healthy": 1, "warning": 2, "critical": 3}
    inverse = {value: key for key, value in rank.items()}
    return inverse[max((rank.get(status, 0) for status in statuses), default=0)]
