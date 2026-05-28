#!/usr/bin/env python3
"""
TRAPP2-1 — FRED macro series fetcher and summarizer.

Fetches required FRED series into data/macro/*.json and writes a consolidated
summary to data/macro_trade.json.

Output format:
{
  "fetched_at": "2026-05-28T14:30:00",
  "series": {
    "GDP": {"latest_value": 28178.1, "date": "2026-04-01", "title": "Gross Domestic Product", "frequency": "quarterly"},
    "INDPRO": {"latest_value": 123.45, "date": "2026-04-01", "title": "Industrial Production Index", "frequency": "monthly"},
    ...
  }
}
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import MACRO, DATA, log, write_json, utc_now_iso

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Core macro series used by the signal engine.
FRED_SERIES = {
    "INDPRO": "Industrial Production Index",
    "T10Y2Y": "10-Year Minus 2-Year Treasury Constant Maturity Spread",
    "BAMLH0A0HYM2": "ICE BofA US High Yield Option-Adjusted Spread",
    "VIXCLS": "CBOE Volatility Index (VIX) Close",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "CPIAUCSL": "Consumer Price Index for All Urban Consumers: All Items",
    "GDP": "Gross Domestic Product",
}

DEFAULT_OBSERVATION_START = "2010-01-01"
REQUEST_DELAY_SECONDS = 0.2


def fetch_json(url, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log(f"  ✗ Fetch error for {url}: {exc}")
        return None


def fetch_series(series_id, api_key):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": DEFAULT_OBSERVATION_START,
    }
    url = f"{FRED_API_BASE}?{urllib.parse.urlencode(params)}"
    log(f"Fetching {series_id}...")
    return fetch_json(url)


def save_series(series_id, data):
    path = MACRO / f"{series_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data, compact=False)
    log(f"  ✓ Saved {path.relative_to(Path.cwd())}")
    return path


def main():
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        log("Missing FRED_API_KEY environment variable")
        return 1

    MACRO.mkdir(parents=True, exist_ok=True)

    consolidated = {
        "fetched_at": utc_now_iso(),
        "series": {},
    }

    for series_id, title in FRED_SERIES.items():
        data = fetch_series(series_id, api_key)
        if not data or not isinstance(data, dict):
            log(f"  ✗ Skipping {series_id}: no data returned")
            continue

        observations = data.get("observations")
        if not observations or not isinstance(observations, list):
            log(f"  ✗ Skipping {series_id}: invalid observations")
            continue

        save_series(series_id, data)

        latest = observations[-1]
        consolidated["series"][series_id] = {
            "latest_value": latest.get("value"),
            "date": latest.get("date"),
            "title": title,
            "frequency": data.get("frequency", "unknown"),
        }
        log(f"  ✓ {series_id}: {latest.get('value')} as of {latest.get('date')}")
        time.sleep(REQUEST_DELAY_SECONDS)

    output_file = DATA / "macro_trade.json"
    write_json(output_file, consolidated, compact=False)
    log(f"Wrote consolidated macro summary → {output_file}")
    return 0 if consolidated["series"] else 1


if __name__ == "__main__":
    sys.exit(main())
