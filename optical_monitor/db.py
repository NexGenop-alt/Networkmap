from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from collector.parsers.ciena_parser import PortReading
from optical_monitor.topology import load_topology


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "optical.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    import os

    return Path(os.getenv("OPTICAL_DB", str(DEFAULT_DB)))


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                clli TEXT,
                mgmt_suffix TEXT,
                svg_x REAL,
                svg_y REAL,
                equipment TEXT,
                tier TEXT,
                node_type TEXT
            );

            CREATE TABLE IF NOT EXISTS links (
                id TEXT PRIMARY KEY,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                speed TEXT,
                fiber_type TEXT,
                color TEXT,
                transport TEXT,
                from_port TEXT,
                to_port TEXT,
                FOREIGN KEY(from_node) REFERENCES nodes(id),
                FOREIGN KEY(to_node) REFERENCES nodes(id)
            );

            CREATE TABLE IF NOT EXISTS optical_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                node_id TEXT NOT NULL,
                port TEXT NOT NULL,
                lane INTEGER,
                rx_dbm REAL,
                tx_dbm REAL,
                tx_bias_ma REAL,
                temperature_c REAL,
                rx_low_alarm REAL,
                rx_low_warning REAL,
                oper_status TEXT,
                in_crc_errors INTEGER DEFAULT 0,
                in_errors INTEGER DEFAULT 0,
                out_discards INTEGER DEFAULT 0,
                out_errors INTEGER DEFAULT 0,
                description TEXT,
                uptime TEXT,
                port_speed TEXT,
                operational_state TEXT,
                vendor_serial TEXT,
                vendor_pn TEXT,
                spec_compliance TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS collector_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_poll TEXT,
                last_success TEXT,
                mode TEXT,
                error_count INTEGER DEFAULT 0,
                last_error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_readings_node_time
                ON optical_readings(node_id, port, timestamp);
            CREATE INDEX IF NOT EXISTS idx_readings_time ON optical_readings(timestamp);
            CREATE INDEX IF NOT EXISTS idx_readings_latest
                ON optical_readings(node_id, port, lane, timestamp);
            """
        )
        seed_topology(conn)


def seed_topology(conn: sqlite3.Connection) -> None:
    topology = load_topology()
    conn.executemany(
        """
        INSERT INTO nodes (id, name, clli, mgmt_suffix, svg_x, svg_y, equipment, tier, node_type)
        VALUES (:id, :name, :clli, :suffix, :x, :y, :equipment, :tier, :type)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, clli=excluded.clli, mgmt_suffix=excluded.mgmt_suffix,
            svg_x=excluded.svg_x, svg_y=excluded.svg_y, equipment=excluded.equipment,
            tier=excluded.tier, node_type=excluded.node_type
        """,
        [
            {
                "id": node["id"],
                "name": node["name"],
                "clli": node.get("clli"),
                "suffix": node.get("suffix"),
                "x": node.get("x"),
                "y": node.get("y"),
                "equipment": node.get("equipment") or node.get("details"),
                "tier": node.get("tier"),
                "type": node.get("type", "router"),
            }
            for node in topology["nodes"]
        ],
    )
    conn.executemany(
        """
        INSERT INTO links (id, from_node, to_node, speed, fiber_type, color, transport, from_port, to_port)
        VALUES (:id, :from_node, :to_node, :speed, :fiber_type, :color, :transport, :from_port, :to_port)
        ON CONFLICT(id) DO UPDATE SET
            from_node=excluded.from_node, to_node=excluded.to_node, speed=excluded.speed,
            fiber_type=excluded.fiber_type, color=excluded.color, transport=excluded.transport,
            from_port=excluded.from_port, to_port=excluded.to_port
        """,
        [
            {
                "id": link["id"],
                "from_node": link["from"],
                "to_node": link["to"],
                "speed": link.get("speed"),
                "fiber_type": link.get("type"),
                "color": link.get("color"),
                "transport": link.get("transport"),
                "from_port": (link.get("ports") or {}).get("from"),
                "to_port": (link.get("ports") or {}).get("to"),
            }
            for link in topology["links"]
        ],
    )


def insert_port_reading(
    conn: sqlite3.Connection,
    node_id: str,
    reading: PortReading,
    timestamp: str | None = None,
) -> None:
    ts = timestamp or utc_now()
    lanes = reading.lanes or []
    raw = json.dumps(asdict(reading), default=str)
    aggregate = {
        "timestamp": ts,
        "node_id": node_id,
        "port": reading.port_number or "unknown",
        "lane": None,
        "rx_dbm": reading.rx_power_avg,
        "tx_dbm": reading.tx_power_avg,
        "tx_bias_ma": None,
        "temperature_c": reading.temperature_c,
        "rx_low_alarm": reading.rx_low_alarm_threshold,
        "rx_low_warning": reading.rx_low_warning_threshold,
        "oper_status": reading.oper_status or reading.operational_state,
        "in_crc_errors": reading.in_crc_errors,
        "in_errors": reading.in_errors,
        "out_discards": reading.out_discards,
        "out_errors": reading.out_errors,
        "description": reading.description,
        "uptime": reading.uptime,
        "port_speed": reading.port_speed,
        "operational_state": reading.operational_state,
        "vendor_serial": reading.vendor_serial,
        "vendor_pn": reading.vendor_pn,
        "spec_compliance": reading.spec_compliance,
        "raw_json": raw,
    }
    _insert_row(conn, aggregate)
    for lane in lanes:
        row = aggregate | {
            "lane": lane.lane_number,
            "rx_dbm": lane.rx_power_dbm,
            "tx_dbm": lane.tx_power_dbm,
            "tx_bias_ma": lane.tx_laser_bias_ma,
            "rx_low_alarm": lane.rx_low_alarm,
            "rx_low_warning": lane.rx_low_warning,
        }
        _insert_row(conn, row)


def _insert_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO optical_readings (
            timestamp, node_id, port, lane, rx_dbm, tx_dbm, tx_bias_ma, temperature_c,
            rx_low_alarm, rx_low_warning, oper_status, in_crc_errors, in_errors,
            out_discards, out_errors, description, uptime, port_speed, operational_state,
            vendor_serial, vendor_pn, spec_compliance, raw_json
        ) VALUES (
            :timestamp, :node_id, :port, :lane, :rx_dbm, :tx_dbm, :tx_bias_ma, :temperature_c,
            :rx_low_alarm, :rx_low_warning, :oper_status, :in_crc_errors, :in_errors,
            :out_discards, :out_errors, :description, :uptime, :port_speed, :operational_state,
            :vendor_serial, :vendor_pn, :spec_compliance, :raw_json
        )
        """,
        row,
    )


def set_collector_status(mode: str, ok: bool, error: str | None = None) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO collector_status (id, last_poll, last_success, mode, error_count, last_error)
            VALUES (1, :last_poll, :last_success, :mode, :error_count, :last_error)
            ON CONFLICT(id) DO UPDATE SET
                last_poll=excluded.last_poll,
                last_success=CASE WHEN :ok THEN excluded.last_success ELSE collector_status.last_success END,
                mode=excluded.mode,
                error_count=collector_status.error_count + :error_increment,
                last_error=excluded.last_error
            """,
            {
                "last_poll": now,
                "last_success": now if ok else None,
                "mode": mode,
                "error_count": 0 if ok else 1,
                "error_increment": 0 if ok else 1,
                "last_error": error,
                "ok": 1 if ok else 0,
            },
        )
