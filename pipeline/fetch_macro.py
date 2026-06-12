#!/usr/bin/env python3
"""
fetch_macro_trade.py — Pull US trade-balance series from FRED and write
data/macro_trade.json. Monthly cadence.

Uses the FRED API key from the FED_API_KEY environment variable (wired into
the TRAPP2-1 repo secrets). FRED series pulled:
  BOPGSTB  — Trade Balance: Goods (Balance of Payments basis), monthly, $M
  EXPGS    — Exports of Goods & Services, quarterly (BEA), $B
  IMPGS    — Imports of Goods & Services, quarterly (BEA), $B
  BOPGEXP  — Exports of Goods (BOP basis), monthly, $M
  BOPGIMP  — Imports of Goods (BOP basis), monthly, $M
  BOPTEXP  — Exports of Goods & Services (BOP basis), monthly, $M  (bonus)
  BOPTIMP  — Imports of Goods & Services (BOP basis), monthly, $M  (bonus)

The browser reads data/macro_trade.json and displays the latest print plus a
short history sparkline in the Global Trade tab.

If this should live inside an existing fetch_macro.py, paste the FRED_TRADE_SERIES
dict and the fetch loop into that file's FRED section — output shape is the same.

Requires: stdlib only.
"""
import json
import os
import sys
import datetime
import urllib.request
import urllib.parse

FRED_KEY = os.environ.get("FED_API_KEY")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OUT_PATH = os.path.join(REPO_ROOT, "data", "macro_trade.json")

# series_id -> (label, units, cadence)
FRED_TRADE_SERIES = {
    "BOPGSTB": ("Goods Trade Balance (BOP)", "USD millions", "monthly"),
    "BOPGEXP": ("Goods Exports (BOP)", "USD millions", "monthly"),
    "BOPGIMP": ("Goods Imports (BOP)", "USD millions", "monthly"),
    "BOPTEXP": ("Goods & Services Exports (BOP)", "USD millions", "monthly"),
    "BOPTIMP": ("Goods & Services Imports (BOP)", "USD millions", "monthly"),
    "EXPGS":   ("Exports of Goods & Services (BEA)", "USD billions", "quarterly"),
    "IMPGS":   ("Imports of Goods & Services (BEA)", "USD billions", "quarterly"),
}

# How many recent observations to keep per series (for the sparkline).
HISTORY_POINTS = 36


def fetch_series(series_id):
    """Return {'latest': {date,value}, 'history': [{date,value}...]} or None."""
    if not FRED_KEY:
        print("   ! FED_API_KEY not set", file=sys.stderr)
        return None
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": HISTORY_POINTS,
    })
    url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "valuatio-macro"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"   ! {series_id}: {e}", file=sys.stderr)
        return None
    obs = data.get("observations", [])
    points = []
    for o in obs:
        v = o.get("value")
        if v in (".", "", None):
            continue
        try:
            points.append({"date": o["date"], "value": float(v)})
        except ValueError:
            continue
    if not points:
        return None
    # API returned newest-first; reverse to chronological for the sparkline.
    points.reverse()
    latest = points[-1]
    prev = points[-2] if len(points) >= 2 else None
    return {
        "latest": latest,
        "prev": prev,
        "history": points,
    }


def main():
    if not FRED_KEY:
        print("FED_API_KEY / FRED_API_KEY not set — cannot fetch FRED.", file=sys.stderr)
        sys.exit(1)

    series_out = {}
    for sid, (label, units, cadence) in FRED_TRADE_SERIES.items():
        res = fetch_series(sid)
        if not res:
            print(f"   skip {sid}", file=sys.stderr)
            continue
        latest = res["latest"]
        prev = res["prev"]
        change = None
        if prev and prev["value"] != 0:
            change = round((latest["value"] - prev["value"]) / abs(prev["value"]) * 100, 2)
        series_out[sid] = {
            "label": label,
            "units": units,
            "cadence": cadence,
            "latest": latest,
            "prevValue": prev["value"] if prev else None,
            "changePct": change,
            "history": res["history"],
        }
        print(f"   {sid}: {latest['date']} = {latest['value']:,.0f} {units}"
              + (f" ({change:+.1f}% MoM)" if change is not None else ""))

    out = {
        "_schema": "valuatio-macro-trade-v1",
        "_description": "US trade-balance series from FRED. Monthly cadence; "
                        "US monthly trade prints ~45 days after the reference month.",
        "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "source": "FRED (api.stlouisfed.org)",
        "series": series_out,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(series_out)} FRED trade series → {OUT_PATH}")


if __name__ == "__main__":
    main()
