"""Build a replayable items file from public GDELT headlines.

One item per US trading day: the prompt a news-sentiment classifier would have
seen at a fixed time of day, built from the previous --days days of headlines.
There is no live label in a public dataset, so score consistency against an
arm (e.g. --reference-arm opus).

  python examples/demo/make_items.py --start 2026-10-15 --end 2026-11-11 \\
      --at 13:15 --out out/demo_items.jsonl
  python -m lje.replay --items out/demo_items.jsonl --arms configs/arms.toml --out out/demo_runs.jsonl
  python -m lje.evals.consistency --items out/demo_items.jsonl --runs out/demo_runs.jsonl \\
      --arms configs/arms.toml --reference-arm opus
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lje.sources import gdelt  # noqa: E402

TEMPLATE = ROOT / "configs" / "prompts" / "equity_sentiment.txt"


def build_prompt(template: str, headlines: list[dict], days: int) -> str:
    text = "\n".join(f"- [{h['date']}] {h['title']}" for h in headlines)
    return template.format(n=len(headlines), days=days, headlines=text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="first session date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="last session date YYYY-MM-DD")
    ap.add_argument("--at", default="13:15", help="call time UTC (13:15 = 15 min before US open in EDT)")
    ap.add_argument("--days", type=int, default=3, help="headline lookback")
    ap.add_argument("--kind", default="equity", choices=sorted(gdelt.KEYWORDS))
    ap.add_argument("--step-hours", type=int, default=2)
    ap.add_argument("--per-domain", type=int, default=10, help="max headlines per site")
    ap.add_argument("--min-headlines", type=int, default=10)
    ap.add_argument("--out", default="out/demo_items.jsonl")
    a = ap.parse_args(argv)

    template = TEMPLATE.read_text(encoding="utf-8")
    hh, mm = (int(x) for x in a.at.split(":"))
    d = datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last = datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    with open(out, "w", encoding="utf-8") as f:
        while d <= last:
            if d.weekday() < 5:                      # US holidays are not excluded
                t = d.replace(hour=hh, minute=mm)
                st = {}
                hl = gdelt.headlines(a.kind, t - timedelta(days=a.days), t,
                                     step_hours=a.step_hours, per_domain=a.per_domain, stats=st)
                if len(hl) >= a.min_headlines:
                    f.write(json.dumps({
                        "id": f"{a.kind}-{t:%Y%m%d}", "kind": a.kind, "ts_utc": t.isoformat(),
                        "prompt": build_prompt(template, hl, a.days),
                        "source": "gdelt", "n_headlines": len(hl), "source_stats": st,
                    }, ensure_ascii=False) + "\n")
                    n_ok += 1
                print(f"{t:%Y-%m-%d} headlines={len(hl)} {st}", flush=True)
            d += timedelta(days=1)
    print(f"wrote {n_ok} items -> {out}")


if __name__ == "__main__":
    main()
