import os
import re
import logging
import dataclasses
from pathlib import Path
from datetime import datetime, timedelta

# Import the DB and Parser tools we've built
from optical_monitor.db import connect, init_db, is_file_processed, mark_file_processed, _insert_row
from collector.parsers.ciena_parser import parse_port_output

log = logging.getLogger("etl_crawler")

def extract_port_chunks(raw_text: str) -> dict[str, str]:
    """
    Slices a multi-port node file into individual port strings.
    Searches for the command prompts (e.g., '>show xcvrs xcvr 34') 
    and groups all output for that specific port together.
    """
    chunks = {}
    # Matches the prompt, command, port number, and captures everything up to the next prompt
    pattern = re.compile(r'>show \w+ \w+ ([\d/]+).*?(?=\n.*?>show |\Z)', re.DOTALL)
    
    for match in pattern.finditer(raw_text):
        port = match.group(1)
        chunk_text = match.group(0)
        
        if port not in chunks:
            chunks[port] = ""
        chunks[port] += "\n" + chunk_text
        
    return chunks

def run_etl_pipeline(base_dir: str, days_back: int = 3):
    """
    Crawls the cabinet_logs directory, skips old folders, and ingests new files.
    """
    init_db()
    base_path = Path(base_dir)
    
    if not base_path.exists():
        log.error(f"Directory '{base_dir}' not found.")
        return

    # SMART CUTOFF: Only scan folders from the last few days to avoid scanning years of data
    cutoff_date = datetime.now() - timedelta(days=days_back)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    
    with connect() as conn:
        # 1. Iterate over Date Folders (e.g., 2026-07-02)
        for date_folder in sorted(base_path.iterdir()):
            if not date_folder.is_dir():
                continue
                
            folder_date = date_folder.name
            
            # Skip folders older than our cutoff
            if folder_date < cutoff_str:
                continue

            log.info(f"Scanning date folder: {folder_date}")

            # 2. Iterate over Node Folders (e.g., ELCJCALA-CIE5164-001)
            for node_folder in date_folder.iterdir():
                if not node_folder.is_dir():
                    continue
                    
                node_id = node_folder.name

                # 3. Iterate over the time-stamped .txt files
                for log_file in node_folder.glob("*.txt"):
                    filepath = str(log_file.resolve())

                    # IDEMPOTENCY: Check the database to see if this exact file was already read
                    if is_file_processed(conn, filepath):
                        continue
                        
                    log.info(f"Ingesting new file: {log_file.name}")
                    
                    try:
                        raw_text = log_file.read_text(encoding="utf-8-sig", errors="replace")
                        
                        # Split the multi-port file into individual port chunks
                        port_chunks = extract_port_chunks(raw_text)
                        
                        for port, chunk_text in port_chunks.items():
                            # Parse the text using our upgraded Ciena parser
                            reading = parse_port_output(chunk_text)
                            
                            # Fallback in case the parser couldn't find the name in the table
                            reading.port_number = reading.port_number or port
                            
                            # Convert the Dataclass to a Dictionary for your DB function
                            row_dict = dataclasses.asdict(reading)
                            row_dict["node_id"] = node_id
                            
                            # Because QSFP ports have multiple lanes, you'll iterate the lanes to insert
                            # (If it's a single reading with no lanes, just insert it directly)
                            if not reading.lanes:
                                row_dict["lane"] = None
                                _insert_row(conn, row_dict)
                            else:
                                for lane in reading.lanes:
                                    lane_row = row_dict.copy()
                                    lane_row.update(dataclasses.asdict(lane))
                                    # Use lane's specific TX/RX instead of averages
                                    lane_row["rx_dbm"] = lane.rx_power_dbm
                                    lane_row["tx_dbm"] = lane.tx_power_dbm
                                    lane_row["lane"] = lane.lane_number
                                    
                                    _insert_row(conn, lane_row)
                            
                        # BOOKMARK: Mark this file as successfully ingested in the database
                        mark_file_processed(conn, filepath)
                        
                    except Exception as exc:
                        log.exception(f"Failed to process {log_file.name}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # You can set days_back=7 to look back a full week, or days_back=1 for just today/yesterday.
    run_etl_pipeline("cabinet_logs", days_back=3)