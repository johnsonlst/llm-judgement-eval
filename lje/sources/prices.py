"""Daily prices and per-session returns for outcome evals.

Daily CSV format (what `fetch` writes):  date,symbol,open,close

A *session* label is a judgement made before the open of a US trading day.
Its outcome is measured from that day's open, so the label could not have
seen any of it:

  r_close   open -> same-day close
  r_1d      open -> next session's close
  r_5d      open -> close 4 sessions later (one trading week)
  prev_1d   prior close-to-close return (known before the open; a baseline)

  python -m lje.sources.prices --symbols QQQ,SPY,IWM,GLD --start 2026-03-01 \\
      --end 2026-11-12 --out cache/daily.csv           # needs: pip install yfinance
"""
import argparse
import csv
from pathlib import Path


def fetch(symbols: list[str], start: str, end: str, out: str | Path) -> int:
    """Download daily open/close with yfinance (optional dependency)."""
    import yfinance as yf
    rows = []
    for sym in symbols:
        df = yf.download(sym, start=start, end=end, auto_adjust=False, progress=False,
                         multi_level_index=False)
        for ts, r in df.iterrows():
            rows.append({"date": ts.strftime("%Y-%m-%d"), "symbol": sym,
                         "open": float(r["Open"]), "close": float(r["Close"])})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["date", "symbol", "open", "close"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def load_daily(path: str | Path) -> dict[str, list[tuple[str, float, float]]]:
    """symbol -> [(date, open, close), ...] sorted by date."""
    by: dict[str, list] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["open"] and r["close"]:
                by.setdefault(r["symbol"], []).append((r["date"], float(r["open"]), float(r["close"])))
    return {s: sorted(v) for s, v in by.items()}


def session_returns(bars: list[tuple[str, float, float]], date: str) -> dict | None:
    """Returns measured from the open of `date`; None if it was not a trading day."""
    idx = {d: i for i, (d, _, _) in enumerate(bars)}
    i = idx.get(date)
    if i is None:
        return None
    o = bars[i][1]

    def close(j):
        return bars[j][2] if j < len(bars) else None

    out = {"r_close": close(i) / o - 1}
    out["r_1d"] = close(i + 1) / o - 1 if close(i + 1) else None
    out["r_5d"] = close(i + 4) / o - 1 if close(i + 4) else None
    out["prev_1d"] = bars[i - 1][2] / bars[i - 2][2] - 1 if i >= 2 else None
    return out


def attach(labels: list[dict], daily: dict, symbols_by_kind: dict[str, list[str]]) -> list[dict]:
    """labels: [{date, kind, label, ...}] -> one row per (label, symbol) with returns."""
    rows = []
    for lab in labels:
        for sym in symbols_by_kind.get(lab.get("kind", ""), []):
            rets = session_returns(daily.get(sym, []), lab["date"])
            if rets:
                rows.append({**lab, "symbol": sym, **rets})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch daily open/close prices (yfinance)")
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusive")
    ap.add_argument("--out", default="cache/daily.csv")
    a = ap.parse_args(argv)
    n = fetch(a.symbols.split(","), a.start, a.end, a.out)
    print(f"wrote {n} rows -> {a.out}")


if __name__ == "__main__":
    main()
