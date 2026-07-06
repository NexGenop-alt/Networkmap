"""
Ciena Waveserver / PKT-200 CLI Parser
======================================
Parses output from three Ciena CLI commands per port:
  1. `show et et <port>`   → ETTP table (port description, oper status, uptime, error counters)
  2. `show x x <port>`     → XCVR tables (vendor data, serial, spec compliance, diagnostics with per-lane optical)

The output format is pipe-delimited key-value tables. Each table has a header
line like `+--- TABLE NAME ---+` followed by `| KEY | VALUE |` rows.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


VENDOR_PN_MAP = {
    "180-3590-900": "200G SR QSFP-DD",
    "180-3370-900": "200G LR QSFP-DD",
    "XCVR-Q10V01": "100G-LR4",
    "XCVR-Q40V31": "100G-ZR4",
    "Q28R-LR4-CIE": "100G-LR4",
    "XCVR-Q30V31": "100G-ER4",
    "Q28R-ZR4-CIE": "100G-ZR4",
    "XCVR-D01LR1": "100G-LR1",
}


@dataclass
class LaneReading:
    """Optical readings for a single lane."""
    lane_number: int
    rx_power_dbm: Optional[float] = None
    tx_power_dbm: Optional[float] = None
    tx_laser_bias_ma: Optional[float] = None
    # Thresholds from the optic itself
    rx_high_alarm: Optional[float] = None
    rx_low_alarm: Optional[float] = None
    rx_high_warning: Optional[float] = None
    rx_low_warning: Optional[float] = None
    tx_high_alarm: Optional[float] = None
    tx_low_alarm: Optional[float] = None
    tx_high_warning: Optional[float] = None
    tx_low_warning: Optional[float] = None
    # Alarm/warning status flags
    rx_high_alarm_status: bool = False
    rx_low_alarm_status: bool = False
    rx_high_warning_status: bool = False
    rx_low_warning_status: bool = False
    tx_high_alarm_status: bool = False
    tx_low_alarm_status: bool = False
    tx_high_warning_status: bool = False
    tx_low_warning_status: bool = False
    # -- From XCVR DIAGNOSTICS --
    temperature_c: Optional[float] = None
    temperature_high_alarm: Optional[float] = None
    temperature_low_alarm: Optional[float] = None
    temperature_high_warning: Optional[float] = None
    temperature_low_warning: Optional[float] = None

    voltage_v: Optional[float] = None
    voltage_high_alarm: Optional[float] = None
    voltage_low_alarm: Optional[float] = None
    voltage_high_warning: Optional[float] = None
    voltage_low_warning: Optional[float] = None

    power_consumption_w: Optional[float] = None


@dataclass
class PortReading:
    """Complete parsed data for a single port."""
    # -- Time and Meta --
    timestamp: Optional[str] = None
    
    # -- From ETTP table --
    port_number: str = ""
    description: str = ""
    oper_status: str = ""              # "UP" or "DOWN"
    uptime: str = ""                   # e.g. "64 days, 1:48:32"
    port_speed: str = ""               # e.g. "100Gb"
    # Error counters
    in_crc_errors: int = 0
    in_errors: int = 0
    out_discards: int = 0
    out_errors: int = 0
    # -- From XCVR DETAILS --
    operational_state: str = ""        # "up" / "down"
    xcvr_type: str = ""                # "QSFP28"
    actual_mode: str = ""              # "100GE"
    # -- From XCVR VENDOR-DATA --
    vendor_serial: str = ""            # e.g. "A40912AE6099"
    vendor_pn: str = ""
    spec_compliance: str = ""          # Human readable alias or base spec
    # -- From XCVR DIAGNOSTICS --
    temperature_c: Optional[float] = None
    voltage_v: Optional[float] = None
    power_consumption_w: Optional[float] = None
    # Per-lane optical data
    lanes: list[LaneReading] = field(default_factory=list)

    @property
    def rx_power_avg(self) -> Optional[float]:
        vals = [l.rx_power_dbm for l in self.lanes if l.rx_power_dbm is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def tx_power_avg(self) -> Optional[float]:
        vals = [l.tx_power_dbm for l in self.lanes if l.tx_power_dbm is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def rx_low_alarm_threshold(self) -> Optional[float]:
        for l in self.lanes:
            if l.rx_low_alarm is not None:
                return l.rx_low_alarm
        return None

    @property
    def rx_low_warning_threshold(self) -> Optional[float]:
        for l in self.lanes:
            if l.rx_low_warning is not None:
                return l.rx_low_warning
        return None

    @property
    def has_any_alarm(self) -> bool:
        for l in self.lanes:
            if any([
                l.rx_high_alarm_status, l.rx_low_alarm_status,
                l.rx_high_warning_status, l.rx_low_warning_status,
                l.tx_high_alarm_status, l.tx_low_alarm_status,
                l.tx_high_warning_status, l.tx_low_warning_status,
            ]):
                return True
        return False


def _extract_value(text: str, key_pattern: str) -> Optional[str]:
    pattern = rf'\|\s*{key_pattern}\s*\|\s*(.+?)\s*\|'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        val = match.group(1).strip()
        return val if val else None
    return None


def _extract_float(text: str, key_pattern: str) -> Optional[float]:
    val = _extract_value(text, key_pattern)
    if val and val != '-':
        try:
            return float(val)
        except ValueError:
            return None
    return None


def _parse_spec_compliance(text: str) -> str:
    val = _extract_value(text, r'Specification Compliance')
    if val:
        match = re.search(r'(\d+GBASE[-\w]+)', val)
        return match.group(1) if match else val
    return ""

def _safe_float(match: Optional[re.Match]) -> Optional[float]:
    """Safely convert a regex match to float, ignoring dashes."""
    if match and match.group(1) != '-':
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def parse_port_output(raw_output: str) -> PortReading:
    reading = PortReading()

    # --- Extract Timestamp ---
    timestamp_match = re.search(r'\*\*\*\s*(.+?)\s*\*\*\*', raw_output)
    if timestamp_match:
        reading.timestamp = timestamp_match.group(1).strip()

    # --- ETTP section ---
    reading.port_number = _extract_value(raw_output, r'Name') or ""
    reading.description = _extract_value(raw_output, r'Description') or ""
    reading.port_speed = _extract_value(raw_output, r'Port Speed') or ""

    # --- ETTP STATE section ---
    reading.oper_status = _extract_value(raw_output, r'Oper Status') or ""
    reading.uptime = _extract_value(raw_output, r'Duration Since Last Oper Change') or ""

    # --- ETTP STATISTICS section ---
    reading.in_crc_errors = int(_extract_value(raw_output, r'In Crc Error Packets') or 0)
    reading.in_errors = int(_extract_value(raw_output, r'In Errors') or 0)
    reading.out_discards = int(_extract_value(raw_output, r'Out Discards\b') or 0)
    reading.out_errors = int(_extract_value(raw_output, r'Out Errors') or 0)

    # --- XCVR DETAILS section ---
    reading.operational_state = _extract_value(raw_output, r'Operational State') or ""
    reading.xcvr_type = _extract_value(raw_output, r'Type\s*(?=\|)') or ""
    reading.actual_mode = _extract_value(raw_output, r'Actual Mode') or ""

    # --- XCVR VENDOR-DATA section ---
    reading.vendor_serial = _extract_value(raw_output, r'Vendor Serial Number') or ""
    
    raw_pn = _extract_value(raw_output, r'Vendor PN') or ""
    reading.vendor_pn = raw_pn
    
    # Map Vendor PN to display alias for the UI, fallback to standard compliance extraction
    mapped_pn = VENDOR_PN_MAP.get(raw_pn)
    if mapped_pn:
        reading.spec_compliance = mapped_pn
    else:
        reading.spec_compliance = _parse_spec_compliance(raw_output)

    # --- XCVR DIAGNOSTICS section ---
    
    # 1. Temperature Block
    temp_block = re.search(r'Temperature \(deg C\)(.*?)(?=Voltage \(V\)|Power Consumption \(W\)|Rx Power \(dBm\)|\Z)', raw_output, re.DOTALL)
    if temp_block:
        tb = temp_block.group(1)
        reading.temperature_c = _safe_float(re.search(r'Current\s*\|\s*([-\d.]+)', tb))
        reading.temperature_high_alarm = _safe_float(re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', tb))
        reading.temperature_low_alarm = _safe_float(re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', tb))
        reading.temperature_high_warning = _safe_float(re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', tb))
        reading.temperature_low_warning = _safe_float(re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', tb))

    # 2. Voltage Block
    volt_block = re.search(r'Voltage \(V\)(.*?)(?=Power Consumption \(W\)|Rx Power \(dBm\)|\Z)', raw_output, re.DOTALL)
    if volt_block:
        vb = volt_block.group(1)
        reading.voltage_v = _safe_float(re.search(r'Current\s*\|\s*([-\d.]+)', vb))
        reading.voltage_high_alarm = _safe_float(re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', vb))
        reading.voltage_low_alarm = _safe_float(re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', vb))
        reading.voltage_high_warning = _safe_float(re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', vb))
        reading.voltage_low_warning = _safe_float(re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', vb))

    # 3. Power Consumption Block
    power_match = re.search(r'Power Consumption \(W\).*?Current\s*\|\s*([-\d.]+)', raw_output, re.DOTALL)
    reading.power_consumption_w = _safe_float(power_match)

    # --- Per-lane optical data ---
    diag_section = raw_output[raw_output.find('XCVR DIAGNOSTICS'):] if 'XCVR DIAGNOSTICS' in raw_output else ""
    
    # Split by Rx Power to dynamically handle 1, 2, or 4 lane optics without needing Lane Headers
    parts = re.split(r'Rx Power \(dBm\)', diag_section)
    
    lane_index = 1
    for part in parts[1:]:  # Skip the first split (general diag info)
        lane = LaneReading(lane_number=lane_index)
        
        # Split into RX and TX chunks
        rx_tx_split = re.split(r'Tx Power \(dBm\)', part)
        rx_text = rx_tx_split[0]
        tx_text = rx_tx_split[1] if len(rx_tx_split) > 1 else ""
        
        # --- RX Parsing ---
        current_rx = re.search(r'Current\s*\|\s*([-\d.]+)', rx_text)
        if current_rx:
            lane.rx_power_dbm = float(current_rx.group(1))
            
        ha = re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', rx_text)
        la = re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', rx_text)
        hw = re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', rx_text)
        lw = re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', rx_text)
        if ha: lane.rx_high_alarm = float(ha.group(1))
        if la: lane.rx_low_alarm = float(la.group(1))
        if hw: lane.rx_high_warning = float(hw.group(1))
        if lw: lane.rx_low_warning = float(lw.group(1))
        
        lane.rx_high_alarm_status = bool(re.search(r'High Alarm Status\s*\|\s*True', rx_text, re.I))
        lane.rx_low_alarm_status = bool(re.search(r'Low Alarm Status\s*\|\s*True', rx_text, re.I))
        lane.rx_high_warning_status = bool(re.search(r'High Warning Status\s*\|\s*True', rx_text, re.I))
        lane.rx_low_warning_status = bool(re.search(r'Low Warning Status\s*\|\s*True', rx_text, re.I))

        # --- TX Parsing ---
        # Using re.search automatically halts at the *first* match, ignoring the secondary Laser Temp sets
        current_tx = re.search(r'Current\s*\|\s*([-\d.]+)', tx_text)
        if current_tx:
            lane.tx_power_dbm = float(current_tx.group(1))
            
        ha_tx = re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', tx_text)
        la_tx = re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', tx_text)
        hw_tx = re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', tx_text)
        lw_tx = re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', tx_text)
        if ha_tx: lane.tx_high_alarm = float(ha_tx.group(1))
        if la_tx: lane.tx_low_alarm = float(la_tx.group(1))
        if hw_tx: lane.tx_high_warning = float(hw_tx.group(1))
        if lw_tx: lane.tx_low_warning = float(lw_tx.group(1))

        lane.tx_high_alarm_status = bool(re.search(r'High Alarm Status\s*\|\s*True', tx_text, re.I))
        lane.tx_low_alarm_status = bool(re.search(r'Low Alarm Status\s*\|\s*True', tx_text, re.I))
        lane.tx_high_warning_status = bool(re.search(r'High Warning Status\s*\|\s*True', tx_text, re.I))
        lane.tx_low_warning_status = bool(re.search(r'Low Warning Status\s*\|\s*True', tx_text, re.I))

        # Check for bias if present in older models
        bias = re.search(r'Tx Laser Bias \(mA\).*?Current\s*\|\s*([-\d.]+)', tx_text, re.DOTALL)
        if bias:
            lane.tx_laser_bias_ma = float(bias.group(1))

        reading.lanes.append(lane)
        lane_index += 1

    return reading


# --- SSH command definitions ---
ETTP_COMMAND = 'show ettps ettp {port} | grep "Desc\|Change\|Port\|In Packets\|Out Packets\|Errors\|Crc\|Status\|---"'
XCVR_COMMAND = 'show xcvrs xcvr {port} | inc "XCVR\|PN\|Serial\|(deg C)\|Current\|(V)\|(W)\|dBm\|Threshold"'

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8-sig') as f:
            raw = f.read()
        
        result = parse_port_output(raw)
        
        print(f"Timestamp: {result.timestamp}")
        print(f"Port: {result.port_number}")
        print(f"Description: {result.description}")
        print(f"Oper Status: {result.oper_status}")
        print(f"Uptime: {result.uptime}")
        print(f"Speed: {result.port_speed}")
        print(f"In CRC Errors: {result.in_crc_errors}")
        print(f"In Errors: {result.in_errors}")
        print(f"Out Discards: {result.out_discards}")
        print(f"Out Errors: {result.out_errors}")
        print(f"Operational State: {result.operational_state}")
        print(f"Serial: {result.vendor_serial}")
        print(f"Mapped Spec: {result.spec_compliance} (Raw PN: {result.vendor_pn})")
        print(f"Temperature: {result.temperature_c} °C")
        print(f"Voltage: {result.voltage_v} V")
        print(f"Power: {result.power_consumption_w} W")
        print(f"Lanes: {len(result.lanes)}")
        for lane in result.lanes:
            print(f"  Lane {lane.lane_number}: RX={lane.rx_power_dbm} dBm, TX={lane.tx_power_dbm} dBm, Bias={lane.tx_laser_bias_ma} mA")
            print(f"    RX Thresholds: alarm=[{lane.rx_low_alarm}, {lane.rx_high_alarm}] warning=[{lane.rx_low_warning}, {lane.rx_high_warning}]")
            print(f"    TX Thresholds: alarm=[{lane.tx_low_alarm}, {lane.tx_high_alarm}] warning=[{lane.tx_low_warning}, {lane.tx_high_warning}]")
        print(f"Average RX: {result.rx_power_avg} dBm")
        print(f"Average TX: {result.tx_power_avg} dBm")
        print(f"Any alarms: {result.has_any_alarm}")
        print(f"Optic Low Alarm Threshold: {result.rx_low_alarm_threshold} dBm")
        print(f"Optic Low Warning Threshold: {result.rx_low_warning_threshold} dBm")
    else:
        print("Usage: python ciena_parser.py <logfile>")