#!/usr/bin/env python3
"""
TRAPP2 — Consolidated FRED macro trade series aggregator.

Reads individual FRED series from data/macro/*.json (created by fetch_macro.py)
and writes a consolidated data/macro_trade.json with latest values for each series.

Output format:
{
  "fetched_at": "2026-05-28T14:30:00",
  "series": {
    "GDP": {"latest_value": 28178.1, "date": "2026-04-01"},
    "INDPRO": {"latest_value": 123.45, "date": "2026-04-01"},
    ...
  }
}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import MACRO, DATA, log, read_json, write_json, utc_now_iso


def main():
    if not MACRO.exists():
        log(f"Macro directory does not exist: {MACRO}")
        return 1

    macro_files = sorted(MACRO.glob("*.json"))
    if not macro_files:
        log(f"No macro series files found in {MACRO}")
        return 1

    consolidated = {
        "fetched_at": utc_now_iso(),
        "series": {}
    }

    for file_path in macro_files:
        series_id = file_path.stem
        data = read_json(file_path)
        
        if not data or not isinstance(data, dict):
            log(f"  ⚠ Skipping {series_id}: invalid format")
            continue
        
        observations = data.get("observations", [])
        if not observations:
            log(f"  ⚠ Skipping {series_id}: no observations")
            continue
        
        # Get latest observation (assumes sorted)
        latest = observations[-1]
        consolidated["series"][series_id] = {
            "latest_value": latest.get("value"),
            "date": latest.get("date"),
            "title": data.get("title", series_id),
            "frequency": data.get("frequency", "unknown"),
        }
        log(f"  ✓ {series_id}: {latest.get('value')} as of {latest.get('date')}")

    output_file = DATA / "macro_trade.json"
    write_json(output_file, consolidated, compact=False)
    log(f"Consolidated {len(consolidated['series'])} series → {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
