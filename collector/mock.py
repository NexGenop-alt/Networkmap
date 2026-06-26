from __future__ import annotations

import copy
import random
from pathlib import Path

from collector.parsers.ciena_parser import PortReading, parse_port_output
from optical_monitor.topology import node_ports


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    ROOT / "collector" / "parsers" / "sample_Device1.log",
    ROOT / "collector" / "parsers" / "sample_Device2.log",
]


def generate_mock_readings() -> list[tuple[str, PortReading]]:
    base = [
        parse_port_output(path.read_text(encoding="utf-8-sig"))
        for path in SAMPLES
    ]
    readings: list[tuple[str, PortReading]] = []
    degraded = {"LND": -11.4, "BNA": -12.1, "IMC": -14.2, "MAX": -14.7}
    noisy = {"SCR", "4MC", "GST", "BNA"}

    for node_id, ports in node_ports().items():
        for index, port in enumerate(ports):
            reading = copy.deepcopy(base[(hash(node_id + port) + index) % len(base)])
            reading.port_number = port
            reading.description = f"{node_id} {port} optical monitor"
            reading.in_crc_errors = random.randint(1, 12) if node_id in noisy and random.random() < 0.35 else 0
            reading.in_errors = reading.in_crc_errors
            reading.out_discards = random.randint(1, 3) if node_id in noisy and random.random() < 0.18 else 0

            target_rx = degraded.get(node_id)
            if target_rx is None:
                target_rx = random.uniform(-5.2, -1.0)
            for lane in reading.lanes:
                lane.rx_power_dbm = round(target_rx + random.uniform(-0.45, 0.45), 2)
                lane.tx_power_dbm = round(random.uniform(-2.8, -1.4) + random.uniform(-0.18, 0.18), 2)
                lane.tx_laser_bias_ma = round(random.uniform(45.0, 58.0), 2)
                if lane.rx_low_alarm is None:
                    lane.rx_low_alarm = -13.6
                if lane.rx_low_warning is None:
                    lane.rx_low_warning = -10.6
                lane.rx_low_alarm_status = lane.rx_power_dbm <= lane.rx_low_alarm
                lane.rx_low_warning_status = lane.rx_power_dbm <= lane.rx_low_warning

            reading.temperature_c = round(random.uniform(34.0, 44.5), 1)
            readings.append((node_id, reading))
    return readings

