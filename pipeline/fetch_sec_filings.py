#!/usr/bin/env python3
"""
fetch_sec_filings.py — Pull recent SEC filing metadata per company (10-K, 10-Q,
8-K, and others) from EDGAR and write data/sec_filings.json. This complements
fetch_13f.py: where 13F covers what funds hold, this covers each COMPANY's own
regulatory filings — annual/quarterly reports (earnings) and 8-K material events.

Reads tickers from the repo's tickers.txt (US equities only — foreign/FX/futures
have no EDGAR CIK and are skipped). Maps ticker→CIK via SEC's company_tickers.json,
then pulls the most recent filings per company from its submissions feed.

Output: data/sec_filings.json keyed by ticker:
  { "AAPL": { "cik": "...", "filings": [
      { "form": "10-K", "filed": "2025-11-01", "period": "2025-09-28",
        "accession": "...", "primaryDoc": "...", "url": "https://www.sec.gov/..." },
      ...
  ] } }

The app reads this to show a "Recent SEC Filings" section per company and to
feed an "earnings recency" signal into the engine (a company that just filed a
10-K/10-Q is in a known fundamental state; stale filings = more uncertainty).

EDGAR requires a descriptive User-Agent — set EDGAR_UA. Quarterly/monthly cadence
is plenty since filings are infrequent. stdlib only.
"""
import json
import os
import sys
import time
import datetime
import urllib.request

EDGAR_UA = "collinmcgough@gmail.com"

# Forms worth surfacing. 10-K/10-Q = earnings (annual/quarterly), 8-K = material
# events, others give a fuller picture. Keep the most recent N per company.
INTERESTING_FORMS = {"10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "20-F", "40-F", "6-K", "DEF 14A", "S-1", "424B"}
MAX_FILINGS_PER_COMPANY = 12

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
TICKERS_PATH = os.path.join(REPO_ROOT, "tickers.txt")
OUT_PATH = os.path.join(REPO_ROOT, "data", "sec_filings.json")

SEC_HEADERS = {"User-Agent": EDGAR_UA, "Accept-Encoding": "gzip, deflate"}


def _get(url, is_json=False):
    req = urllib.request.Request(url, headers=SEC_HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if raw[:2] == b"\x1f\x8b":
                    import gzip
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", errors="replace")
                return json.loads(text) if is_json else text
        except Exception as e:
            print(f"   retry {attempt+1} {url}: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
    return None


def load_tickers():
    """Read tickers.txt, skipping comments and obvious non-equities."""
    out = []
    try:
        with open(TICKERS_PATH) as f:
            for line in f:
                t = line.strip()
                if not t or t.startswith("#"):
                    continue
                # Skip non-US-equity instrument forms (no EDGAR CIK):
                #   =X FX, =F futures, ^ indices, -USD crypto, .PVT private,
                #   .<exchange> foreign listings, OCC option tickers (long+digits)
                if any(x in t for x in ("=X", "=F", "-USD", ".PVT")) or t.startswith("^") or "." in t:
                    continue
                if len(t) > 6 and any(c.isdigit() for c in t):  # option ticker
                    continue
                out.append(t.upper())
    except FileNotFoundError:
        print(f"tickers.txt not found at {TICKERS_PATH}", file=sys.stderr)
    return out


def build_ticker_cik_map():
    """SEC publishes ticker→CIK at company_tickers.json. Returns {TICKER: cik10}."""
    data = _get("https://www.sec.gov/files/company_tickers.json", is_json=True)
    if not data:
        return {}
    out = {}
    # Shape: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
    for rec in data.values():
        tic = rec.get("ticker", "").upper()
        cik = rec.get("cik_str")
        if tic and cik is not None:
            out[tic] = str(cik).zfill(10)
    return out


def recent_filings(cik):
    """Pull recent interesting filings for one CIK from its submissions feed."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _get(url, is_json=True)
    if not data:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accns = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    periods = recent.get("reportDate", [])
    docs = recent.get("primaryDocument", [])
    out = []
    for i, form in enumerate(forms):
        if form not in INTERESTING_FORMS:
            continue
        acc_nodash = accns[i].replace("-", "")
        out.append({
            "form": form,
            "filed": filed[i] if i < len(filed) else None,
            "period": periods[i] if i < len(periods) else None,
            "accession": accns[i],
            "primaryDoc": docs[i] if i < len(docs) else None,
            "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{acc_nodash}/{docs[i]}") if i < len(docs) and docs[i] else
                   (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                    f"&CIK={cik}&type={form}"),
        })
        if len(out) >= MAX_FILINGS_PER_COMPANY:
            break
    return out


def main():
    tickers = load_tickers()
    if not tickers:
        print("No equity tickers found.", file=sys.stderr)
        sys.exit(1)
    print(f"[sec] {len(tickers)} equity tickers to check")

    cik_map = build_ticker_cik_map()
    if not cik_map:
        print("Could not load ticker→CIK map from EDGAR.", file=sys.stderr)
        sys.exit(1)
    time.sleep(0.3)

    out = {}
    hit = 0
    for tic in tickers:
        cik = cik_map.get(tic)
        if not cik:
            continue  # no EDGAR CIK (e.g. some ADRs, ETFs)
        filings = recent_filings(cik)
        time.sleep(0.25)  # polite to EDGAR
        if not filings:
            continue
        # Most recent 10-K or 10-Q = latest "earnings" filing
        latest_earnings = next((f for f in filings if f["form"] in ("10-K", "10-Q", "20-F", "6-K")), None)
        out[tic] = {
            "cik": cik,
            "latestEarnings": latest_earnings,
            "filings": filings,
            "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
        }
        hit += 1
        if hit % 25 == 0:
            print(f"   ...{hit} companies with filings")

    doc = {
        "_schema": "valuatio-sec-filings-v1",
        "_description": "Recent SEC filing metadata per company (10-K/10-Q earnings, "
                        "8-K events, etc.) from EDGAR. Quarterly/monthly cadence.",
        "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "companies": out,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(doc, f, indent=2)
    print(f"[sec] wrote filings for {hit} companies → {OUT_PATH}")


if __name__ == "__main__":
    main()
