"""
Ciena Waveserver / PKT-200 CLI Parser
======================================
Parses output from three Ciena CLI commands per port:
  1. `show et et <port>`   → ETTP table (port description, oper status, uptime, error counters)
  2. `show x x <port>`     → XCVR tables (vendor data, serial, spec compliance, diagnostics with per-lane optical)

The output format is pipe-delimited key-value tables. Each table has a header
line like `+--- TABLE NAME ---+` followed by `| KEY | VALUE |` rows.

All three commands are run per port. The raw output is concatenated and passed
to `parse_port_output()` which returns a single structured dict.

CLI commands (the actual commands were sanitized in the logs but follow this pattern):
  Device> show et et <port_number>
  Device> show x x <port_number>
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LaneReading:
    """Optical readings for a single QSFP28 lane (1-4)."""
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


@dataclass
class PortReading:
    """Complete parsed data for a single port."""
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
    spec_compliance: str = ""          # e.g. "100GBASE-LR4"
    # -- From XCVR DIAGNOSTICS --
    temperature_c: Optional[float] = None
    voltage_v: Optional[float] = None
    power_consumption_w: Optional[float] = None
    # Per-lane optical data (QSFP28 = 4 lanes)
    lanes: list[LaneReading] = field(default_factory=list)

    @property
    def rx_power_avg(self) -> Optional[float]:
        """Average RX power across all lanes."""
        vals = [l.rx_power_dbm for l in self.lanes if l.rx_power_dbm is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def tx_power_avg(self) -> Optional[float]:
        """Average TX power across all lanes."""
        vals = [l.tx_power_dbm for l in self.lanes if l.tx_power_dbm is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    @property
    def rx_low_alarm_threshold(self) -> Optional[float]:
        """Use the optic's own low alarm threshold (same across lanes)."""
        for l in self.lanes:
            if l.rx_low_alarm is not None:
                return l.rx_low_alarm
        return None

    @property
    def rx_low_warning_threshold(self) -> Optional[float]:
        """Use the optic's own low warning threshold."""
        for l in self.lanes:
            if l.rx_low_warning is not None:
                return l.rx_low_warning
        return None

    @property
    def has_any_alarm(self) -> bool:
        """True if any lane has any alarm or warning flag set."""
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
    """Extract a value from a pipe-delimited Ciena table row.
    
    Matches lines like:
      |   Some Key Name           | some_value    |
    """
    pattern = rf'\|\s*{key_pattern}\s*\|\s*(.+?)\s*\|'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        val = match.group(1).strip()
        return val if val else None
    return None


def _extract_float(text: str, key_pattern: str) -> Optional[float]:
    """Extract a float value from a table row."""
    val = _extract_value(text, key_pattern)
    if val and val != '-':
        try:
            return float(val)
        except ValueError:
            return None
    return None


def _extract_bool(text: str, key_pattern: str) -> bool:
    """Extract a boolean status flag (True/False string)."""
    val = _extract_value(text, key_pattern)
    return val.lower() == 'true' if val else False


def _parse_spec_compliance(text: str) -> str:
    """Extract just the standard name from the compliance string.
    
    Input:  "Extended-Spec-Compliance-100GBASE-LR4"
    Output: "100GBASE-LR4"
    """
    val = _extract_value(text, r'Specification Compliance')
    if val:
        # Strip the "Extended-Spec-Compliance-" prefix if present
        match = re.search(r'(\d+GBASE[-\w]+)', val)
        return match.group(1) if match else val
    return ""


def parse_port_output(raw_output: str) -> PortReading:
    """
    Parse the concatenated output of all CLI commands for a single port.
    
    Expected input is the full text from running:
      show et et <port>
      show x x <port>
    
    The output contains multiple pipe-delimited tables:
      - ETTP (port config)
      - ETTP STATE (oper status, uptime)
      - ETTP STATISTICS (counters)
      - XCVR DETAILS (admin/oper state, type)
      - XCVR VENDOR-DATA (serial, spec compliance)
      - XCVR DIAGNOSTICS (temperature, per-lane TX/RX/bias)
    """
    reading = PortReading()

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
    reading.vendor_pn = _extract_value(raw_output, r'Vendor PN') or ""
    reading.spec_compliance = _parse_spec_compliance(raw_output)

    # --- XCVR DIAGNOSTICS section ---
    reading.temperature_c = _extract_float(raw_output, r'Temperature \(deg C\)\s*\|\s*\|\s*Current')
    reading.voltage_v = _extract_float(raw_output, r'Voltage \(V\)\s*\|\s*\|\s*Current')
    reading.power_consumption_w = _extract_float(raw_output, r'Power Consumption \(W\)\s*\|\s*\|\s*Current')

    # The temperature/voltage parsing above may fail because the "Current" is on
    # the NEXT line after the header. Use a different approach: find the section
    # then grab "Current" value right after it.
    temp_match = re.search(
        r'Temperature \(deg C\)\s*\|[^|]*\|\s*\n\s*\|\s*Current\s*\|\s*([-\d.]+)',
        raw_output
    )
    if temp_match:
        reading.temperature_c = float(temp_match.group(1))
    else:
        # Fallback: simpler pattern for single-line layout
        temp_match2 = re.search(r'Temperature \(deg C\).*?Current\s*\|\s*([-\d.]+)', raw_output, re.DOTALL)
        if temp_match2:
            reading.temperature_c = float(temp_match2.group(1))

    voltage_match = re.search(r'Voltage \(V\).*?Current\s*\|\s*([-\d.]+)', raw_output, re.DOTALL)
    if voltage_match:
        reading.voltage_v = float(voltage_match.group(1))

    power_match = re.search(r'Power Consumption \(W\).*?Current\s*\|\s*([-\d.]+)', raw_output, re.DOTALL)
    if power_match:
        reading.power_consumption_w = float(power_match.group(1))

    # --- Per-lane optical data ---
    # Split DIAGNOSTICS section into lane blocks.
    # Each lane starts with "Lane Number | N" and contains RX, TX, and Bias data.
    diag_section = raw_output[raw_output.find('XCVR DIAGNOSTICS'):] if 'XCVR DIAGNOSTICS' in raw_output else ""
    
    lane_blocks = re.split(r'(?=\|\s*Lane Number\s*\|)', diag_section)
    
    for block in lane_blocks:
        lane_num_match = re.search(r'Lane Number\s*\|\s*(\d+)', block)
        if not lane_num_match:
            continue
        
        lane = LaneReading(lane_number=int(lane_num_match.group(1)))
        
        # Find RX Power section within this lane block
        rx_section = re.search(
            r'Rx Power \(dBm\)(.*?)(?=Tx Power \(dBm\)|Tx Laser Bias|Lane Number|\Z)',
            block, re.DOTALL
        )
        if rx_section:
            rx_text = rx_section.group(1)
            current = re.search(r'Current\s*\|\s*([-\d.]+)', rx_text)
            if current:
                lane.rx_power_dbm = float(current.group(1))
            
            # Thresholds
            ha = re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', rx_text)
            la = re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', rx_text)
            hw = re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', rx_text)
            lw = re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', rx_text)
            if ha: lane.rx_high_alarm = float(ha.group(1))
            if la: lane.rx_low_alarm = float(la.group(1))
            if hw: lane.rx_high_warning = float(hw.group(1))
            if lw: lane.rx_low_warning = float(lw.group(1))
            
            # Status flags
            lane.rx_high_alarm_status = bool(re.search(r'High Alarm Status\s*\|\s*True', rx_text, re.I))
            lane.rx_low_alarm_status = bool(re.search(r'Low Alarm Status\s*\|\s*True', rx_text, re.I))
            lane.rx_high_warning_status = bool(re.search(r'High Warning Status\s*\|\s*True', rx_text, re.I))
            lane.rx_low_warning_status = bool(re.search(r'Low Warning Status\s*\|\s*True', rx_text, re.I))

        # Find TX Power section within this lane block
        tx_section = re.search(
            r'Tx Power \(dBm\)(.*?)(?=Tx Laser Bias|Lane Number|\Z)',
            block, re.DOTALL
        )
        if tx_section:
            tx_text = tx_section.group(1)
            current = re.search(r'Current\s*\|\s*([-\d.]+)', tx_text)
            if current:
                lane.tx_power_dbm = float(current.group(1))
            
            ha = re.search(r'High Alarm Threshold\s*\|\s*([-\d.]+)', tx_text)
            la = re.search(r'Low Alarm Threshold\s*\|\s*([-\d.]+)', tx_text)
            hw = re.search(r'High Warning Threshold\s*\|\s*([-\d.]+)', tx_text)
            lw = re.search(r'Low Warning Threshold\s*\|\s*([-\d.]+)', tx_text)
            if ha: lane.tx_high_alarm = float(ha.group(1))
            if la: lane.tx_low_alarm = float(la.group(1))
            if hw: lane.tx_high_warning = float(hw.group(1))
            if lw: lane.tx_low_warning = float(lw.group(1))

            lane.tx_high_alarm_status = bool(re.search(r'High Alarm Status\s*\|\s*True', tx_text, re.I))
            lane.tx_low_alarm_status = bool(re.search(r'Low Alarm Status\s*\|\s*True', tx_text, re.I))
            lane.tx_high_warning_status = bool(re.search(r'High Warning Status\s*\|\s*True', tx_text, re.I))
            lane.tx_low_warning_status = bool(re.search(r'Low Warning Status\s*\|\s*True', tx_text, re.I))

        # Bias current
        bias_section = re.search(
            r'Tx Laser Bias \(mA\)(.*?)(?=Laser Temperature|Lane Number|\Z)',
            block, re.DOTALL
        )
        if bias_section:
            bias_text = bias_section.group(1)
            current = re.search(r'Current\s*\|\s*([-\d.]+)', bias_text)
            if current:
                lane.tx_laser_bias_ma = float(current.group(1))

        reading.lanes.append(lane)

    return reading


# --- SSH command definitions ---

# These are the actual commands to run on each Ciena box.
# The logs show the prompt pattern: "DeviceName> show <cmd> <cmd> <port>"
# Command 1 - ETTP (port stats/state):
ETTP_COMMAND = "show et et {port}"
# Command 2 - XCVR (transceiver details + vendor + diagnostics):
XCVR_COMMAND = "show x x {port}"

# Full collection sequence for one port:
# 1. SSH into the node
# 2. Run ETTP_COMMAND.format(port=port_number) → capture output
# 3. Run XCVR_COMMAND.format(port=port_number) → capture output
# 4. Concatenate both outputs
# 5. Pass to parse_port_output() → get PortReading


# --- Quick validation test ---

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8-sig') as f:
            raw = f.read()
        
        result = parse_port_output(raw)
        
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
        print(f"Spec: {result.spec_compliance}")
        print(f"Temperature: {result.temperature_c} °C")
        print(f"Voltage: {result.voltage_v} V")
        print(f"Power: {result.power_consumption_w} W")
        print(f"Lanes: {len(result.lanes)}")
        for lane in result.lanes:
            print(f"  Lane {lane.lane_number}: RX={lane.rx_power_dbm} dBm, TX={lane.tx_power_dbm} dBm, Bias={lane.tx_laser_bias_ma} mA")
            print(f"    RX Thresholds: alarm=[{lane.rx_low_alarm}, {lane.rx_high_alarm}] warning=[{lane.rx_low_warning}, {lane.rx_high_warning}]")
        print(f"Average RX: {result.rx_power_avg} dBm")
        print(f"Average TX: {result.tx_power_avg} dBm")
        print(f"Any alarms: {result.has_any_alarm}")
        print(f"Optic Low Alarm Threshold: {result.rx_low_alarm_threshold} dBm")
        print(f"Optic Low Warning Threshold: {result.rx_low_warning_threshold} dBm")
    else:
        print("Usage: python ciena_parser.py <logfile>")
        print("  Parses a Ciena CLI log file and prints extracted data.")
