"""Replay archived prompts under experimental arms.

Items file (JSONL), one per archived call:
  {"id": "...", "kind": "equity", "ts_utc": "...", "prompt": "...",
   "reference": "bearish"}          # reference = what the live system got (optional)

Arms config (TOML), e.g. configs/arms.toml:
  [arms.opus]          model="claude-opus-5-5"   mode="trim" transform="orig"    reps=2
  [arms.opus_shuffle]  model="claude-opus-5-5"   mode="trim" transform="shuffle"
  [arms.haiku]         model="claude-haiku-5-5"  mode="trim"

Results append to --out keyed by (id, arm, rep); finished keys are skipped, so
an interrupted run (e.g. a usage limit) resumes where it stopped. Error rows
are written but not counted as done.

  python -m lje.replay --items items.jsonl --arms configs/arms.toml --out out/runs.jsonl
"""
import argparse
import hashlib
import json
import sys
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .archive import load
from .parse import DEFAULT_LABELS, parse_label
from .providers import PROVIDERS
from .providers.claude_cli import total_tokens
from .transforms import TRANSFORMS


def load_arms(path: str | Path) -> tuple[dict, dict]:
    cfg = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    run = cfg.get("run", {})
    arms = {}
    for name, a in cfg.get("arms", {}).items():
        arms[name] = {"model": a["model"], "mode": a.get("mode", "trim"),
                      "transform": a.get("transform", "orig"), "reps": int(a.get("reps", 1)),
                      "provider": a.get("provider", "claude_cli"), "system": a.get("system")}
        if arms[name]["transform"] not in TRANSFORMS:
            raise ValueError(f"arm {name}: unknown transform {arms[name]['transform']!r}")
        if arms[name]["provider"] not in PROVIDERS:
            raise ValueError(f"arm {name}: unknown provider {arms[name]['provider']!r}")
    return run, arms


def seed_for(item_id: str, rep: int) -> int:
    """Stable across runs and machines (unlike hash(), which is salted)."""
    digest = hashlib.sha256(f"{item_id}:{rep}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def done_keys(out: Path) -> set:
    if not out.exists():
        return set()
    return {(r["id"], r["arm"], r["rep"]) for r in load(out) if r.get("label")}


def run_one(item: dict, arm_name: str, arm: dict, rep: int, labels, timeout: int) -> dict:
    seed = seed_for(str(item["id"]), rep)
    prompt = TRANSFORMS[arm["transform"]](item["prompt"], seed)
    out = PROVIDERS[arm["provider"]](prompt, arm["model"], mode=arm["mode"],
                                     system=arm["system"], timeout=timeout)
    rec = {"id": item["id"], "kind": item.get("kind"), "arm": arm_name, "rep": rep,
           "transform": arm["transform"], "seed": seed if arm["transform"] != "orig" else None,
           "ts_utc": datetime.now(timezone.utc).isoformat(), **out}
    if not out.get("error"):
        rec["label"], rec["reason"] = parse_label(out.get("raw", ""), labels)
        if rec["label"] is None:
            rec["error"] = "unparsed"
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--items", required=True)
    ap.add_argument("--arms", required=True, help="TOML arms config")
    ap.add_argument("--out", default="out/runs.jsonl")
    ap.add_argument("--only", default="", help="comma-separated arm names to run")
    ap.add_argument("--limit", type=int, default=0, help="first N items (pilot)")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--max-errors", type=int, default=10)
    ap.add_argument("--blackout-utc", default="",
                    help="e.g. 13-21: refuse to start in these UTC hours (shared quota with a live system)")
    a = ap.parse_args(argv)

    if a.blackout_utc:
        lo, hi = (int(x) for x in a.blackout_utc.split("-"))
        h = datetime.now(timezone.utc).hour
        if (lo <= h < hi) if lo < hi else (h >= lo or h < hi):
            sys.exit(f"inside blackout {a.blackout_utc} UTC; not starting")

    run_cfg, arms = load_arms(a.arms)
    if a.only:
        arms = {k: v for k, v in arms.items() if k in a.only.split(",")}
    labels = tuple(run_cfg.get("labels", DEFAULT_LABELS))
    timeout = int(run_cfg.get("timeout", 120))
    workers = a.workers or int(run_cfg.get("workers", 4))

    items = load(a.items)
    if a.limit:
        items = items[:a.limit]
    out = Path(a.out)
    done = done_keys(out)
    todo = [(it, n, arm, rep) for it in items for n, arm in arms.items()
            for rep in range(arm["reps"]) if (it["id"], n, rep) not in done]
    print(f"items={len(items)} arms={list(arms)} todo={len(todo)} already_done={len(done)}", flush=True)
    if not todo:
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    ok = errors = tokens = 0
    t0 = time.monotonic()
    with ThreadPoolExecutor(workers) as ex, open(out, "a", encoding="utf-8") as fout:
        futs = [ex.submit(run_one, it, n, arm, rep, labels, timeout) for it, n, arm, rep in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            with lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
            tokens += total_tokens(rec.get("usage"))
            if rec.get("error"):
                errors += 1
                print(f"ERR {rec['id']} {rec['arm']}: {rec['error']} {(rec.get('stderr') or '')[:160]}",
                      flush=True)
                if errors >= a.max_errors:
                    print("too many errors (usage limit?) -> stopping; re-run to resume", flush=True)
                    for f in futs:
                        f.cancel()
                    break
            else:
                ok += 1
            if i % 20 == 0 or i == len(todo):
                el = time.monotonic() - t0
                print(f"{i}/{len(todo)} ok={ok} err={errors} {el:.0f}s tokens={tokens:,}", flush=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
