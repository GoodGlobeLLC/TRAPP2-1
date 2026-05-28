#!/usr/bin/env python3
"""
TRAPP2-1 — World Bank countries and development indicators fetcher.

Fetches World Bank data via their public API (no key required):
- Countries list: https://api.worldbank.org/v2/country
- Development indicators: https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}

Writes consolidated data/worldbank_countried.json with countries and key indicators.

Output format:
{
  "fetched_at": "2026-05-28T14:30:00",
  "countries": [
    {"code": "US", "name": "United States", "region": "North America", "incomeLevel": "High income"},
    ...
  ],
  "indicators": {
    "NY.GDP.MKTP.CD": {"name": "GDP (current US$)", "description": "..."},
    ...
  },
  "latest_data": {
    "US": {"NY.GDP.MKTP.CD": {"value": 27360..., "date": "2023"}},
    ...
  }
}
"""
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import DATA, log, write_json, utc_now_iso


# Key World Bank indicators for macro/economic analysis
INDICATORS = [
    "NY.GDP.MKTP.CD",      # GDP (current US$)
    "NY.GDP.PCAP.CD",      # GDP per capita (current US$)
    "FP.CPI.TOTL.ZG",      # Inflation, consumer prices (annual %)
    "NY.GDP.DEFL.ZS",      # GDP deflator (annual %)
    "SP.URB.TOTL.IN.ZS",   # Urban population (% of total)
    "SP.POP.TOTL",         # Population, total
    "NV.IND.TOTL.CD",      # Industry (ISIC A-F) value added (current US$)
    "NV.AGR.TOTL.CD",      # Agriculture, forestry, and fishing (current US$)
    "TX.VAL.TECH.CD",      # Exports of high-technology products (current US$)
    "TM.VAL.TECH.CD",      # Imports of high-technology products (current US$)
]

# Major economies and trading partners to fetch detailed data for
# Uses 3-letter World Bank country codes
MAJOR_COUNTRIES = [
    "USA", "GBR", "DEU", "FRA", "JPN", "CHN", "IND", "BRA", "CAN", "MEX",
    "AUS", "KOR", "SGP", "NLD", "CHE", "SWE", "NOR", "DNK", "FIN", "ARE",
    "SAU", "RUS", "ZAF", "NGA", "EGY", "TUR", "IDN", "THA", "MYS", "PHL",
]


def fetch_json(url, timeout=30):
    """Fetch JSON from URL with error handling."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        log(f"  ✗ Fetch error: {e}")
        return None


def fetch_countries():
    """Fetch list of countries from World Bank."""
    log("Fetching World Bank countries...")
    url = "https://api.worldbank.org/v2/country?format=json&per_page=500"
    data = fetch_json(url)
    if not data or len(data) < 2:
        return []
    
    countries = []
    for item in data[1]:
        countries.append({
            "code": item.get("id"),
            "name": item.get("name"),
            "region": item.get("region", {}).get("value"),
            "incomeLevel": item.get("incomeLevel", {}).get("value"),
        })
    log(f"  ✓ Fetched {len(countries)} countries")
    return countries


def fetch_indicator_metadata(indicator_code):
    """Fetch metadata for a single indicator."""
    url = f"https://api.worldbank.org/v2/indicator/{indicator_code}?format=json"
    data = fetch_json(url)
    if not data or len(data) < 2 or not data[1]:
        return None
    
    indicator = data[1][0]
    return {
        "code": indicator.get("id"),
        "name": indicator.get("name"),
        "description": indicator.get("description", ""),
        "source": indicator.get("source", {}).get("value"),
    }


def fetch_latest_value(country_code, indicator_code):
    """Fetch latest value for a country/indicator pair."""
    url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}?format=json&per_page=100&date=2015:2026"
    data = fetch_json(url)
    
    if not data or len(data) < 2 or not data[1]:
        return None
    
    # Find first non-null value (newest first)
    for entry in data[1]:
        if entry.get("value") is not None:
            return {
                "value": float(entry.get("value")),
                "date": entry.get("date"),
            }
    return None


def main():
    consolidated = {
        "fetched_at": utc_now_iso(),
        "countries": [],
        "indicators": {},
        "latest_data": {}
    }

    # Fetch countries
    countries = fetch_countries()
    if not countries:
        log("Failed to fetch countries")
        return 1
    
    consolidated["countries"] = countries

    # Fetch indicator metadata
    log(f"Fetching metadata for {len(INDICATORS)} indicators...")
    for indicator_code in INDICATORS:
        metadata = fetch_indicator_metadata(indicator_code)
        if metadata:
            consolidated["indicators"][indicator_code] = metadata
            log(f"  ✓ {indicator_code}: {metadata['name']}")
        time.sleep(0.1)

    # Fetch latest data for each country/indicator
    log(f"Fetching latest data for {len(MAJOR_COUNTRIES)} major countries × {len(INDICATORS)} indicators...")
    call_count = 0
    for country_code in MAJOR_COUNTRIES:
        if country_code not in {c["code"] for c in countries}:
            log(f"  ⚠ {country_code}: not found in countries list")
            continue
        consolidated["latest_data"][country_code] = {}
        for indicator_code in INDICATORS:
            value = fetch_latest_value(country_code, indicator_code)
            if value:
                consolidated["latest_data"][country_code][indicator_code] = value
            call_count += 1
            if call_count % 30 == 0:
                log(f"  • {call_count} API calls...")
                time.sleep(0.5)  # Rate limiting
            else:
                time.sleep(0.08)

    output_file = DATA / "worldbank_countried.json"
    write_json(output_file, consolidated, compact=False)
    log(f"Wrote World Bank data → {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
