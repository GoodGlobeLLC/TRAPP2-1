#!/usr/bin/env python3
"""
TRAPP2 — World Bank country macro fetcher.

Fetches annual country macroeconomic data from the World Bank API.

No API key required.

Outputs:
data/worldbank_countries.json

Included indicators:
- NY.GDP.MKTP.CD     → GDP (current USD)
- NE.EXP.GNFS.ZS    → Exports (% of GDP)
- NE.IMP.GNFS.ZS    → Imports (% of GDP)

API Docs:
:contentReference[oaicite:0]{index=0}
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib import DATA, log, write_json, utc_now_iso

# =========================================================
# CONFIG
# =========================================================

OUTFILE = DATA / "worldbank_countries.json"

BASE_URL = "https://api.worldbank.org/v2/country"

# Most relevant global macro indicators
INDICATORS = {
    "NY.GDP.MKTP.CD": {
        "name": "GDP Current USD",
        "field": "gdp_usd",
    },
    "NE.EXP.GNFS.ZS": {
        "name": "Exports Percent GDP",
        "field": "exports_pct_gdp",
    },
    "NE.IMP.GNFS.ZS": {
        "name": "Imports Percent GDP",
        "field": "imports_pct_gdp",
    },
}

# Pull enough history for long-term analysis
START_YEAR = 1990

# Higher page size reduces API calls substantially
PER_PAGE = 20000


# =========================================================
# HTTP FETCH
# =========================================================

def fetch_json(url):
    """
    Fetch JSON payload from URL.
    """

    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read())

    except Exception as e:
        log(f"  ✗ Request failed: {e}")
        return None


# =========================================================
# FETCH INDICATOR
# =========================================================

def fetch_indicator(indicator_code):
    """
    Fetch all country observations for one indicator.
    """

    params = {
        "format": "json",
        "per_page": PER_PAGE,
    }

    url = (
        f"{BASE_URL}/all/indicator/{indicator_code}?"
        + urllib.parse.urlencode(params)
    )

    payload = fetch_json(url)

    if not payload or len(payload) < 2:
        log(f"  ✗ Invalid payload for {indicator_code}")
        return []

    return payload[1]


# =========================================================
# BUILD COUNTRY DATASET
# =========================================================

def build_dataset():
    """
    Build normalized country/year dataset.
    """

    countries = {}

    for indicator_code, meta in INDICATORS.items():

        log(f"Fetching {indicator_code}")

        observations = fetch_indicator(indicator_code)

        field = meta["field"]

        n_added = 0

        for obs in observations:

            try:
                country = obs.get("country", {})
                iso3 = obs.get("countryiso3code")
                year = obs.get("date")
                value = obs.get("value")

                if not iso3 or iso3 == "":
                    continue

                if iso3 == "WLD":
                    continue

                if not year:
                    continue

                year_int = int(year)

                if year_int < START_YEAR:
                    continue

                if value is None:
                    continue

                country_name = country.get("value", iso3)

                # Initialize country
                if iso3 not in countries:
                    countries[iso3] = {
                        "iso3": iso3,
                        "country": country_name,
                        "annual": {}
                    }

                # Initialize year bucket
                if year not in countries[iso3]["annual"]:
                    countries[iso3]["annual"][year] = {}

                # Store value
                countries[iso3]["annual"][year][field] = value

                n_added += 1

            except Exception:
                continue

        log(f"  ✓ {indicator_code}: {n_added:,} observations")

        # Small delay to avoid hammering API
        time.sleep(0.25)

    return countries


# =========================================================
# MAIN
# =========================================================

def main():

    log("Building World Bank country macro dataset")

    DATA.mkdir(parents=True, exist_ok=True)

    countries = build_dataset()

    output = {
        "fetched_at": utc_now_iso(),
        "source": "World Bank",
        "indicators": {
            code: meta["name"]
            for code, meta in INDICATORS.items()
        },
        "countries": countries,
    }

    write_json(
        OUTFILE,
        output,
        compact=True
    )

    log(f"✓ Wrote {OUTFILE}")
    log(f"✓ Countries: {len(countries):,}")

    return 0


# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    sys.exit(main())
