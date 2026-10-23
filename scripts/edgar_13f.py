#!/usr/bin/env python3
"""Build a 13F consensus from SEC EDGAR (free). Replaces paid 13F aggregators.

For each manager in research/13f_managers.json it downloads the 13F-HR filings,
parses the information table, maps CUSIP -> ticker with OpenFIGI, and writes:
  research/data/13f_holdings.csv   manager, period, filed, ticker, issuer, value_usd, shares
  research/data/13f_consensus.csv  latest quarter: ticker, n_managers, total_value, managers
and prints the consensus plus quarter-over-quarter adds and exits per manager.

SEC fair access: every automated request must carry a User-Agent that names the
operator and a contact email, e.g.  "Jane Doe jane@example.com". Set it with
    export SEC_USER_AGENT="Your Name your-email@example.com"
The script refuses to run without it and never invents one. Max ~5 requests/sec.

Known limits (same as every 13F tool): long US-listed positions only, filed up to
45 days after quarter end; option rows (putCall set) are skipped; values before
2023 were reported in thousands and are scaled.

Usage:
    python scripts/edgar_13f.py                 # all managers, last 4 quarters
    python scripts/edgar_13f.py --quarters 8 --min-managers 2
    python scripts/edgar_13f.py --selftest      # offline parser test
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "research" / "data"
MANAGERS = ROOT / "research" / "13f_managers.json"
CUSIP_CACHE = DATA / "cusip_map.json"
_last = [0.0]


def ua() -> str:
    v = os.getenv("SEC_USER_AGENT", "").strip()
    if "@" not in v or " " not in v:
        sys.exit("Set SEC_USER_AGENT to 'Your Name your-email@example.com' (SEC fair-access rule). "
                 "Refusing to run with an undeclared or invented identity.")
    return v


def http(url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    wait = 0.21 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    h = {"User-Agent": ua()}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    _last[0] = time.time()
    return urllib.request.urlopen(req, timeout=60).read()


def parse_infotable(xml_bytes: bytes, scale: int) -> list[dict]:
    """Return rows of (cusip, issuer, value_usd, shares). Namespace-agnostic."""
    root = ET.fromstring(xml_bytes)
    rows = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "infoTable":
            continue
        d = {c.tag.split("}")[-1]: c for c in el}
        if d.get("putCall") is not None and (d["putCall"].text or "").strip():
            continue  # skip option rows
        sh = d.get("shrsOrPrnAmt")
        shares = 0
        if sh is not None:
            for c in sh:
                if c.tag.split("}")[-1] == "sshPrnamt":
                    shares = int(float(c.text or 0))
        rows.append(dict(cusip=(d["cusip"].text or "").strip().upper(), issuer=(d["nameOfIssuer"].text or "").strip(),
                         value=int(float(d["value"].text or 0)) * scale, shares=shares))
    return rows


def list_filings(cik: int) -> tuple[str, list[dict]]:
    j = json.loads(http(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    r = j["filings"]["recent"]
    out = [dict(filed=r["filingDate"][i], period=r["reportDate"][i], acc=r["accessionNumber"][i])
           for i in range(len(r["form"])) if r["form"][i] == "13F-HR"]
    return j["name"], sorted(out, key=lambda x: x["period"], reverse=True)


def fetch_infotable(cik: int, acc: str) -> bytes:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    idx = json.loads(http(base + "index.json"))
    names = [i["name"] for i in idx["directory"]["item"] if i["name"].lower().endswith(".xml")]
    pick = next((n for n in names if "infotable" in n.lower() or "info_table" in n.lower()), None) \
        or next((n for n in names if "primary_doc" not in n.lower()), None)
    if not pick:
        raise RuntimeError(f"no information table in {acc}")
    return http(base + pick)


def map_cusips(cusips: list[str]) -> dict[str, str]:
    cache = json.loads(CUSIP_CACHE.read_text()) if CUSIP_CACHE.exists() else {}
    todo = [c for c in dict.fromkeys(cusips) if c not in cache]
    for i in range(0, len(todo), 10):  # OpenFIGI keyless limit: 10 per request, 25 requests/min
        chunk = todo[i:i + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]).encode()
        req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": ua()})
        res = json.load(urllib.request.urlopen(req, timeout=60))
        for c, r in zip(chunk, res):
            cache[c] = (r.get("data") or [{}])[0].get("ticker", "")
        time.sleep(2.5)
    CUSIP_CACHE.write_text(json.dumps(cache, indent=0))
    return cache


SELFTEST_XML = b"""<?xml version="1.0"?><informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>UBER TECHNOLOGIES INC</nameOfIssuer><cusip>90353T100</cusip><value>2478000000</value>
<shrsOrPrnAmt><sshPrnamt>30000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>SOME CO</nameOfIssuer><cusip>111111111</cusip><value>5</value>
<shrsOrPrnAmt><sshPrnamt>1</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Put</putCall></infoTable></informationTable>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quarters", type=int, default=4)
    ap.add_argument("--min-managers", type=int, default=2)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        rows = parse_infotable(SELFTEST_XML, 1)
        assert len(rows) == 1 and rows[0]["cusip"] == "90353T100" and rows[0]["value"] == 2478000000, rows
        assert parse_infotable(SELFTEST_XML.replace(b"2478000000", b"2478000"), 1000)[0]["value"] == 2478000000
        print("selftest ok: parses dollars and thousands, skips option rows")
        return
    DATA.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(MANAGERS.read_text())["managers"]
    holdings = []  # (label, period, filed, cusip, issuer, value, shares)
    for m in cfg:
        name, filings = list_filings(m["cik"])
        if m["name_contains"].upper() not in name.upper():
            print(f"[refused] {m['label']}: CIK {m['cik']} is registered as '{name}', not a match; fix the config")
            continue
        for f in filings[:args.quarters]:
            scale = 1000 if f["filed"] < "2023-01-03" else 1
            for r in parse_infotable(fetch_infotable(m["cik"], f["acc"]), scale):
                holdings.append((m["label"], f["period"], f["filed"], r["cusip"], r["issuer"], r["value"], r["shares"]))
        print(f"{m['label']:<20} {name[:40]:<40} {len(filings[:args.quarters])} filings")
    tick = map_cusips([h[3] for h in holdings])
    agg = defaultdict(lambda: defaultdict(float))
    with (DATA / "13f_holdings.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["manager", "period", "filed", "ticker", "issuer", "value_usd", "shares"])
        for lab, per, filed, cus, iss, val, sh in holdings:
            t = tick.get(cus, "") or cus
            w.writerow([lab, per, filed, t, iss, val, sh])
            agg[(lab, per)][t] += val
    periods = sorted({p for _, p in agg})
    if not periods:
        sys.exit("no holdings parsed")
    latest = periods[-1]
    by_t = defaultdict(lambda: [0, 0.0, []])
    for (lab, per), d in agg.items():
        if per != latest:
            continue
        tot = sum(d.values())
        for t, v in d.items():
            by_t[t][0] += 1; by_t[t][1] += v / tot; by_t[t][2].append(lab)
    cons = sorted(((n, w_, t, labs) for t, (n, w_, labs) in by_t.items() if n >= args.min_managers), reverse=True)
    with (DATA / "13f_consensus.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "n_managers", "sum_portfolio_weight", "managers"])
        for n, w_, t, labs in cons:
            w.writerow([t, n, f"{w_:.3f}", ";".join(labs)])
    print(f"\nlatest quarter {latest}: {len(cons)} names held by >= {args.min_managers} managers")
    for n, w_, t, labs in cons[:25]:
        print(f"  {t:<8} {n} managers  weight-sum {w_:.2f}  {', '.join(labs)}")
    if len(periods) > 1:
        prev = periods[-2]
        for lab in sorted({l for l, _ in agg}):
            a, b = agg.get((lab, latest), {}), agg.get((lab, prev), {})
            if a and b:
                print(f"  {lab}: added {sorted(set(a) - set(b))}  exited {sorted(set(b) - set(a))}")


if __name__ == "__main__":
    main()
