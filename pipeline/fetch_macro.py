#!/usr/bin/env python3
"""
TRAPP2 — FRED macro series fetcher.

Reads FRED_API_KEY from env. Writes data/macro/<series_id>.json for each series.
Each file:
{
  "series_id",
  "title",
  "frequency",
  "fetched_at",
  "observations": [{"date", "value"}, ...]
}

Also builds:
data/macro/macro_trade.json

Add free API key from:
:contentReference[oaicite:0]{index=0}

Store it as GitHub repo secret:
FRED_API_KEY
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib import MACRO, log, write_json, utc_now_iso

# =========================================================
# FRED SERIES
# =========================================================
# Format:
# (series_id, title, frequency, observation_start)

SERIES = [
    # Growth
    ("GDP",           "Real GDP",                       "quarterly", "1990-01-01"),
    ("INDPRO",        "Industrial Production",          "monthly",   "1990-01-01"),

    # Trade
    ("BOPGSTB",       "Goods Trade Balance",            "monthly",   "1990-01-01"),
    ("EXPGS",         "Exports of Goods & Services",    "monthly",   "1990-01-01"),
    ("IMPGS",         "Imports of Goods & Services",    "monthly",   "1990-01-01"),
    ("BOPGEXP",       "Goods Exports",                  "monthly",   "1990-01-01"),
    ("BOPGIMP",       "Goods Imports",                  "monthly",   "1990-01-01"),

    # Labor
    ("UNRATE",        "Unemployment Rate",              "monthly",   "1990-01-01"),
    ("PAYEMS",        "Nonfarm Payrolls",               "monthly",   "1990-01-01"),

    # Inflation
    ("CPIAUCSL",      "CPI All Urban Consumers",        "monthly",   "1990-01-01"),
    ("PCEPI",         "PCE Price Index",                "monthly",   "1990-01-01"),

    # Rates / Liquidity
    ("DFF",           "Effective Fed Funds Rate",       "daily",     "2010-01-01"),
    ("M2SL",          "M2 Money Stock",                 "monthly",   "1990-01-01"),

    # Treasury Curve
    ("DGS3MO",        "3-Month Treasury Yield",         "daily",     "2010-01-01"),
    ("DGS2",          "2-Year Treasury Yield",          "daily",     "2010-01-01"),
    ("DGS10",         "10-Year Treasury Yield",         "daily",     "2010-01-01"),
    ("T10Y2Y",        "10Y-2Y Treasury Spread",         "daily",     "2010-01-01"),
    ("T10Y3M",        "10Y-3M Treasury Spread",         "daily",     "2010-01-01"),

    # Credit / Risk
    ("BAMLH0A0HYM2",  "High Yield OAS",                 "daily",     "2010-01-01"),
    ("VIXCLS",        "VIX",                            "daily",     "2010-01-01"),

    # Commodities / FX
    ("DCOILWTICO",    "WTI Crude Oil",                  "daily",     "2010-01-01"),
    ("DEXUSEU",       "USD/EUR Exchange Rate",          "daily",     "2010-01-01"),
]

# Trade series for combined bundle
TRADE_SERIES = {
    "BOPGSTB",
    "EXPGS",
    "IMPGS",
    "BOPGEXP",
    "BOPGIMP",
}


# =========================================================
# FETCH FRED SERIES
# =========================================================

def fetch_series(series_id, api_key, start="2000-01-01"):
    """
    Fetch a single FRED series.
    """

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    }

    url = (
        "https://api.stlouisfed.org/fred/series/observations?"
        + urllib.parse.urlencode(params)
    )

    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            payload = json.loads(r.read())

    except Exception as e:
        log(f"  ✗ {series_id}: {e}")
        return None

    obs = payload.get("observations", [])

    cleaned = []

    for o in obs:
        d = o.get("date")
        v = o.get("value")

        if not d or v in (".", "", None):
            continue

        try:
            cleaned.append({
                "date": d,
                "value": float(v)
            })

        except (ValueError, TypeError):
            continue

    return {
        "series_id": series_id,
        "fetched_at": utc_now_iso(),
        "observations": cleaned,
    }


# =========================================================
# BUILD COMBINED TRADE FILE
# =========================================================

def build_trade_bundle():
    """
    Build combined macro_trade.json
    """

    bundle = {
        "fetched_at": utc_now_iso(),
        "series": {}
    }

    for sid in TRADE_SERIES:

        path = MACRO / f"{sid}.json"

        if not path.exists():
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                bundle["series"][sid] = json.load(f)

        except Exception as e:
            log(f"  ✗ Failed bundling {sid}: {e}")

    write_json(
        MACRO / "macro_trade.json",
        bundle,
        compact=True
    )

    log("  ✓ macro_trade.json")


# =========================================================
# MAIN
# =========================================================

def main():

    api_key = os.environ.get("FRED_API_KEY", "").strip()

    if not api_key:
        log("FRED_API_KEY not set. Skipping macro fetch.")
        log(
            "Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html"
        )
        return 0

    MACRO.mkdir(parents=True, exist_ok=True)

    log(f"Fetching {len(SERIES)} FRED series → {MACRO}")

    n_ok = 0

    for sid, title, frequency, start in SERIES:

        data = fetch_series(
            sid,
            api_key,
            start=start
        )

        if data is None:
            continue

        data["title"] = title
        data["frequency"] = frequency

        write_json(
            MACRO / f"{sid}.json",
            data,
            compact=True
        )

        log(
            f"  ✓ {sid:14s} "
            f"{len(data['observations']):>6d} obs · "
            f"{title}"
        )

        n_ok += 1

        # Be polite to FRED API
        time.sleep(0.15)

    # Build combined trade file
    build_trade_bundle()

    log(f"Wrote {n_ok}/{len(SERIES)} series.")

    return 0


# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    sys.exit(main())
