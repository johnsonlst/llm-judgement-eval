"""Public, reproducible headline source for the harness: GDELT 2.0 bulk GKG files.

GDELT publishes one GKG file every 15 minutes at
  http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip
(~6.5MB zipped, ~1.5K articles). Column 26 ("Extras") carries <PAGE_TITLE>.
The DOC 2.0 search API is rate-limited (HTTP 429), so we use the bulk files.

To keep downloads sane we sample one file every --step-hours (default 3) and
cache only the parsed titles (cache/gdelt/YYYYMMDDHHMMSS.jsonl, ~250KB;
set LJE_GDELT_CACHE to move it); the
zip itself is discarded. Downloads are untrusted data: parsed as plain text,
never executed.

API:
  headlines(kind, start_utc, end_utc, step_hours=3, max_n=60, per_domain=6)
      -> list of {"date": "YYYY-MM-DD", "title", "domain", "url", "ts"}
  most recent first, de-duplicated, filtered by kind keywords + domain lists.

CLI (prefetch a window):
  python -m lje.sources.gdelt --start 2026-10-12 --end 2026-11-12 --step-hours 3
"""
import argparse
import os
import csv
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

CACHE = Path(os.environ.get("LJE_GDELT_CACHE", "cache/gdelt"))
BASE = "http://data.gdeltproject.org/gdeltv2/{}.gkg.csv.zip"
UA = {"User-Agent": "research-harness/0.1"}
csv.field_size_limit(2 ** 31 - 1)

# Mainstream news / markets outlets. Allowlist beats a denylist here: the long
# tail of GDELT is ticker-spam networks and syndicated local reprints.
ALLOW = {
    "reuters.com", "apnews.com", "cnbc.com", "marketwatch.com", "wsj.com",
    "bloomberg.com", "ft.com", "nytimes.com", "washingtonpost.com",
    "finance.yahoo.com", "yahoo.com", "barrons.com", "investing.com",
    "foxbusiness.com", "cnn.com", "bbc.com", "bbc.co.uk", "theguardian.com",
    "forbes.com", "businessinsider.com", "markets.businessinsider.com",
    "axios.com", "seekingalpha.com", "fool.com", "morningstar.com",
    "thestreet.com", "investopedia.com", "economist.com", "npr.org",
    "cbsnews.com", "nbcnews.com", "abcnews.go.com", "usatoday.com",
    "latimes.com", "politico.com", "fortune.com", "kiplinger.com",
    "zerohedge.com", "benzinga.com", "fxstreet.com", "kitco.com",
    "mining.com", "nasdaq.com", "theglobeandmail.com", "scmp.com",
    "aljazeera.com", "independent.co.uk", "telegraph.co.uk", "irishtimes.com",
}

KEYWORDS = {
    "equity": re.compile(
        r"\b(stocks?|stock market|wall street|s&p ?500|nasdaq|dow jones|the dow|"
        r"equities|federal reserve|the fed|fed (?:rate|chair|hike|cut)|rate (?:hike|cut)s?|"
        r"treasury yields?|bond yields?|inflation|cpi|jobs report|payrolls|recession|"
        r"earnings|tariffs?|selloff|sell-off|rally|bear market|bull market|volatility|vix)\b",
        re.I),
    # Gold: a bare "gold"/"silver" match is mostly medals, mining-junior press
    # releases and place names, so require price wording.
    "gold": re.compile(
        r"\b(gold (?:prices?|futures|rate|rates|market|etfs?|demand|rall(?:y|ies)|falls?|fell|"
        r"drops?|dropped|climbs?|rises?|rose|slips?|slipped|eases?|edges?|gains?|jumps?|surges?|"
        r"tumbles?|slides?|hits?|holds?|steadies|record)|spot gold|bullion|precious metals?|xau|"
        r"gold and silver|gold, silver|gold price)\b", re.I),
}

# Per-kind source policy. Equity: allowlist (plenty of mainstream coverage).
# Gold: mainstream coverage is thin, so keyword-gated + denylist of spam/PR wires.
POLICY = {"equity": "allow", "gold": "deny"}
DENY = {
    "tickerreport.com", "themarketsdaily.com", "finanznachrichten.de", "marketbeat.com",
    "etfdailynews.com", "dailypolitical.com", "prnewswire.com", "globenewswire.com",
    "businesswire.com", "accessnewswire.com", "newsfilecorp.com",
}

_TITLE = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _allowed(dom: str, kind: str = "equity") -> bool:
    if POLICY[kind] == "deny":
        return dom not in DENY
    return dom in ALLOW or any(dom.endswith("." + a) for a in ALLOW)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y%m%d%H%M%S")


def _parse_zip(raw: bytes) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(raw))
    out = []
    with z.open(z.namelist()[0]) as fh:
        for r in csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                            delimiter="\t"):
            if len(r) < 27:
                continue
            m = _TITLE.search(r[26])
            if not m:
                continue
            title = html.unescape(m.group(1)).strip()
            if title:
                out.append({"ts": r[1], "url": r[4] or r[3], "title": title})
    return out


def fetch_slot(t: datetime, retries: int = 3) -> list[dict]:
    """Parsed titles for the 15-min file at t (cached). [] if GDELT has no file."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{_stamp(t)}.jsonl"
    if path.exists():
        # split on "\n" only: str.splitlines() also splits on U+2028 etc.,
        # which appear inside some GDELT titles
        return [json.loads(l) for l in path.read_text(encoding="utf-8").split("\n") if l]
    for i in range(retries):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(BASE.format(_stamp(t)), headers=UA),
                                         timeout=90).read()
            rows = _parse_zip(raw)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:          # GDELT occasionally skips a slot
                rows = []
                break
            time.sleep(5 * (i + 1))
        except Exception:
            time.sleep(5 * (i + 1))
    else:
        raise RuntimeError(f"GDELT fetch failed for {_stamp(t)}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    tmp.replace(path)
    return rows


def slots(start: datetime, end: datetime, step_hours: int) -> list[datetime]:
    """On-the-hour slots in [start, end], aligned to multiples of step_hours UTC
    so overlapping windows share cached files."""
    t = start.replace(minute=0, second=0, microsecond=0)
    while t.hour % step_hours:
        t += timedelta(hours=1)
    out = []
    while t <= end:
        if t >= start:
            out.append(t)
        t += timedelta(hours=step_hours)
    return out


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def headlines(kind: str, start: datetime, end: datetime, step_hours: int = 3,
              max_n: int = 60, per_domain: int = 6, stats: dict | None = None) -> list[dict]:
    kw = KEYWORDS[kind]
    seen, per_dom, out = set(), {}, []
    raw_n = kw_n = allow_n = 0
    for t in sorted(slots(start, end, step_hours), reverse=True):   # most recent first
        for a in fetch_slot(t):
            raw_n += 1
            if not kw.search(a["title"]):
                continue
            kw_n += 1
            dom = _domain(a["url"])
            if not _allowed(dom, kind):
                continue
            allow_n += 1
            key = _norm(a["title"])
            if key in seen or per_dom.get(dom, 0) >= per_domain:
                continue
            seen.add(key)
            per_dom[dom] = per_dom.get(dom, 0) + 1
            out.append({"date": f"{a['ts'][:4]}-{a['ts'][4:6]}-{a['ts'][6:8]}",
                        "title": a["title"], "domain": dom, "url": a["url"], "ts": a["ts"]})
    if stats is not None:
        stats.update(raw=raw_n, keyword=kw_n, allowlisted=allow_n, kept_before_cap=len(out),
                     domains=len(per_dom))
    return out[:max_n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (UTC, inclusive)")
    ap.add_argument("--step-hours", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    s = datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    e = datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=23)
    todo = [t for t in slots(s, e, a.step_hours) if not (CACHE / f"{_stamp(t)}.jsonl").exists()]
    print(f"{len(todo)} slots to fetch (step {a.step_hours}h)", flush=True)
    t0, done, errs = time.monotonic(), 0, 0
    with ThreadPoolExecutor(a.workers) as ex:
        for t, fut in [(t, ex.submit(fetch_slot, t)) for t in todo]:
            try:
                fut.result()
            except Exception as ex_:
                errs += 1
                print(f"ERR {t}: {ex_}", flush=True)
            done += 1
            if done % 25 == 0 or done == len(todo):
                print(f"{done}/{len(todo)} errs={errs} {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
