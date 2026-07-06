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
from collector.folder_file_crawler import run_etl_pipeline

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

    import re
    init_db()
    count = 0
    username = os.environ["SSH_USER"]
    password = os.getenv("SSH_PASSWORD")
    key_filename = os.getenv("SSH_KEY")
    for target in targets:
        node_id = target["id"]
        host = target["host"]
        
        # Check if node_id matches the pattern <node>-00<num>
        match = re.match(r'^(.+?)-00(\d+)$', node_id)
        if match:
            base_node_id = match.group(1)   # e.g. "4MC"
            router_num = match.group(2)     # e.g. "1" or "2"
        else:
            base_node_id = node_id
            router_num = None

        if "ports" in target:
            ports = target["ports"]
        else:
            all_ports = node_ports().get(base_node_id, ["35"])
            if router_num:
                ports = [p for p in all_ports if p.startswith(f"{router_num}p")]
            else:
                ports = all_ports

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, username=username, password=password, key_filename=key_filename, timeout=12)
            for port in ports:
                # Prepend the router prefix if not already present in the db port identifier
                db_port = port
                if router_num and not port.startswith(f"{router_num}p"):
                    if port.startswith("p"):
                        db_port = f"{router_num}{port}"
                    else:
                        db_port = f"{router_num}p{port}"
                
                cmd_port = re.sub(r'^\d+', '', port) if router_num else port
                
                raw = _run(client, ETTP_COMMAND.format(port=cmd_port)) + "\n" + _run(client, XCVR_COMMAND.format(port=cmd_port))
                reading = parse_port_output(raw)
                reading.port_number = db_port
                
                with connect() as conn:
                    insert_port_reading(conn, base_node_id, reading)
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
    parser.add_argument("--crawl", action="store_true", help="Crawl local log directories for new files")
    parser.add_argument("--log-dir", type=str, default="cabinet_logs", help="Path to the log directory")
    args = parser.parse_args()
    setup_logging()

    while True:
        try:
            if args.mock:
                collect_mock_once()
            elif args.crawl:
                # Run our new pipeline
                run_etl_pipeline(base_dir=args.log_dir, days_back=3)
            else:
                raise RuntimeError("SSH target config is not yet populated; run with --mock, --crawl, or add targets.")
        except Exception as exc:
            log.exception("collector poll failed")
            set_collector_status("mock" if args.mock else "ssh", False, str(exc))
        
        if args.once:
            break
        
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
