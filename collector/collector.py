from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Iterable

from collector.mock import generate_mock_readings
from collector.parsers.ciena_parser import ETTP_COMMAND, XCVR_COMMAND, parse_port_output
from optical_monitor.db import connect, init_db, insert_port_reading, set_collector_status
from optical_monitor.topology import node_ports


log = logging.getLogger("collector")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler])


def collect_mock_once() -> int:
    init_db()
    readings = generate_mock_readings()
    with connect() as conn:
        for node_id, reading in readings:
            insert_port_reading(conn, node_id, reading)
    set_collector_status("mock", True)
    log.info("mock poll complete: %s port readings", len(readings))
    return len(readings)


def collect_ssh_once(targets: Iterable[dict[str, str]]) -> int:
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("Paramiko is required for SSH mode. Install requirements.txt.") from exc

    init_db()
    count = 0
    username = os.environ["SSH_USER"]
    password = os.getenv("SSH_PASSWORD")
    key_filename = os.getenv("SSH_KEY")
    for target in targets:
        node_id = target["id"]
        host = target["host"]
        ports = target.get("ports") or node_ports().get(node_id, ["35"])
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, username=username, password=password, key_filename=key_filename, timeout=12)
            for port in ports:
                raw = _run(client, ETTP_COMMAND.format(port=port)) + "\n" + _run(client, XCVR_COMMAND.format(port=port))
                reading = parse_port_output(raw)
                if not reading.port_number:
                    reading.port_number = str(port)
                with connect() as conn:
                    insert_port_reading(conn, node_id, reading)
                count += 1
            client.close()
        except Exception as exc:
            log.exception("collection failed for %s at %s", node_id, host)
            set_collector_status("ssh", False, f"{node_id}: {exc}")
    set_collector_status("ssh", True)
    return count


def _run(client, command: str) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=20)
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if err:
        log.warning("command stderr for %s: %s", command, err)
    return stdout.read().decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wyyerd Ciena optical collector")
    parser.add_argument("--mock", action="store_true", help="generate realistic data from parser sample logs")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    parser.add_argument("--interval", type=int, default=int(os.getenv("COLLECT_INTERVAL", "30")))
    args = parser.parse_args()
    setup_logging()

    while True:
        try:
            if args.mock:
                collect_mock_once()
            else:
                raise RuntimeError("SSH target config is not yet populated; run with --mock or add targets.")
        except Exception as exc:
            log.exception("collector poll failed")
            set_collector_status("mock" if args.mock else "ssh", False, str(exc))
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
