"""Outcome report: did the judgement predict anything?

Each row is one label with the returns that followed it:
  {"date", "kind", "symbol", "label", "r_close", "r_1d", ...}

Signed return = +r for BULLISH, -r for BEARISH (NEUTRAL sits out). It is the
P&L of a unit position that follows the label, so the null is 0. Every label
is compared with baselines that read no text at all:

  always_long   +1 every session (the market's drift)
  momentum      sign of the previous session's return

A label only "knows something" if it beats the baselines, not just zero.

  # rows with returns already attached (e.g. data/aots/sessions.csv)
  python -m lje.evals.outcome --rows data/aots/sessions.csv

  # or labels + a daily price file
  python -m lje.evals.outcome --labels labels.csv --daily cache/daily.csv \\
      --symbols equity=QQQ,SPY,IWM --symbols gold=GLD

Rows that share a day (several calls per session) should pass --group date so
the confidence interval resamples whole days.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from ..archive import load
from ..sources import prices
from ..stats import block_bootstrap_ci, bootstrap_ci, perm_test_mean

SIGN = {"bullish": 1, "bearish": -1, "neutral": 0}
HORIZONS = ("r_close", "r_1d", "r_5d")


def read_rows(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix == ".csv":
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = load(path)
    for r in rows:
        r["label"] = str(r.get("label", "")).lower()
        for k, v in list(r.items()):
            if k.startswith(("r_", "prev_")):
                r[k] = float(v) if v not in ("", None) else None
    return rows


def signed(rows: list[dict], signal, horizon: str, group: str | None, n_boot: int) -> dict:
    """Signed-return stats for one signal (a function row -> +1/0/-1/None)."""
    pts = [(signal(r), r[horizon], r.get(group) if group else None) for r in rows
           if r.get(horizon) is not None]
    pts = [(s, x, g) for s, x, g in pts if s]                       # drop 0 / None
    if not pts:
        return {"n": 0}
    sr = [s * x for s, x, _ in pts]
    if group:
        lo, hi = block_bootstrap_ci(sr, [g for *_, g in pts], n_boot=n_boot)
    else:
        lo, hi = bootstrap_ci(sr, n_boot=n_boot)
    sig = [s for s, _, _ in pts]
    # shuffling a constant signal tests nothing; with --group the rows are not
    # independent, so a row-level permutation would overstate significance
    p = (perm_test_mean(sig, [x for _, x, _ in pts], n_perm=n_boot)[1]
         if len(set(sig)) > 1 and not group else None)
    return {"n": len(sr), "signed_bp": sum(sr) / len(sr) * 1e4, "ci_bp": [lo * 1e4, hi * 1e4],
            "hit": sum(v > 0 for v in sr) / len(sr), "perm_p": p}


SIGNALS = {
    "label": lambda r: SIGN.get(r["label"]),
    "always_long": lambda r: 1,
    "momentum": lambda r: (1 if r["prev_1d"] > 0 else -1) if r.get("prev_1d") is not None else None,
}


def report(rows: list[dict], horizons=HORIZONS, group: str | None = None,
           n_boot: int = 10000) -> tuple[str, dict]:
    horizons = [h for h in horizons if any(r.get(h) is not None for r in rows)]
    by = defaultdict(list)
    for r in rows:
        by[(r.get("kind", "all"), r.get("symbol", "-"))].append(r)
    L, out = [], {}
    p = L.append
    p(f"outcome report: {len(rows)} rows" + (f", CI resamples by '{group}'" if group else ""))
    p("signed_bp = mean return of following the signal, in basis points (1bp = 0.01%)\n")
    for (kind, sym), rs in sorted(by.items()):
        mix = Counter(r["label"] for r in rs)
        p(f"== {kind} / {sym} ==  n={len(rs)}  " + " ".join(f"{k}={mix[k]}" for k in SIGN))
        key = f"{kind}/{sym}"
        out[key] = {"n": len(rs), "mix": dict(mix)}
        for h in horizons:
            p(f"-- {h}")
            p(f"   {'by label':<14}{'n':>5}{'mean_bp':>10}{'up%':>7}")
            for lab in SIGN:
                xs = [r[h] for r in rs if r["label"] == lab and r.get(h) is not None]
                if xs:
                    p(f"   {lab:<14}{len(xs):>5}{sum(xs) / len(xs) * 1e4:>10.1f}"
                      f"{sum(x > 0 for x in xs) / len(xs):>7.0%}")
            p(f"   {'signal':<14}{'n':>5}{'signed_bp':>10}{'95% CI':>18}{'hit':>6}{'perm_p':>8}")
            for name, fn in SIGNALS.items():
                s = signed(rs, fn, h, group, n_boot)
                out[key][f"{h}/{name}"] = s
                if s["n"]:
                    p(f"   {name:<14}{s['n']:>5}{s['signed_bp']:>10.1f}"
                      f"   [{s['ci_bp'][0]:>6.1f},{s['ci_bp'][1]:>6.1f}]"
                      f"{s['hit']:>6.0%}"
                      + (f"{s['perm_p']:>8.3f}" if s["perm_p"] is not None else f"{'-':>8}"))
        p("")
    return "\n".join(L), out


def _symbols(specs: list[str]) -> dict[str, list[str]]:
    out = {}
    for spec in specs:
        kind, syms = spec.split("=", 1)
        out[kind] = syms.split(",")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Did the labels predict returns?")
    ap.add_argument("--rows", help="rows with returns attached (CSV or JSONL)")
    ap.add_argument("--labels", help="labels without returns: date,kind,label (CSV or JSONL)")
    ap.add_argument("--daily", help="daily price CSV for --labels (see lje.sources.prices)")
    ap.add_argument("--symbols", action="append", default=[], help="kind=SYM1,SYM2 (repeatable)")
    ap.add_argument("--group", help="resample CIs by this column (e.g. date)")
    ap.add_argument("--horizons", default=",".join(HORIZONS))
    ap.add_argument("--where", action="append", default=[], help="col=value filter (repeatable)")
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--out", help="write the text report here (and .json beside it)")
    a = ap.parse_args(argv)
    if a.rows:
        rows = read_rows(a.rows)
    elif a.labels and a.daily and a.symbols:
        rows = prices.attach(read_rows(a.labels), prices.load_daily(a.daily), _symbols(a.symbols))
    else:
        ap.error("give --rows, or --labels with --daily and --symbols")
    for w in a.where:
        col, val = w.split("=", 1)
        rows = [r for r in rows if str(r.get(col)) == val]
    txt, summary = report(rows, a.horizons.split(","), a.group, a.boot)
    print(txt)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
