"""Consistency report: is the judgement stable, and what does it cost?

Per (kind, arm):
  label mix              does the arm lean one way? (e.g. over-calls NEUTRAL)
  agreement              vs the reference: the live label (item["reference"])
                         or another arm (--reference-arm), Wilson 95% CI
  kappa                  agreement corrected for chance
  format                 share of replies whose first line is a bare label
  tokens / latency       median per call
Plus, for arms with reps >= 2 or a shuffled twin:
  repeat stability       share of items where every rep (and the reference) agree
  order effect           flip rate of a *shuffle* arm minus its *orig* twin

  python -m lje.evals.consistency --items items.jsonl --runs out/runs.jsonl \\
      --arms configs/arms.toml [--reference-arm opus] [--out out/consistency.txt]
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ..archive import load
from ..parse import DEFAULT_LABELS, is_compliant
from ..providers.claude_cli import total_tokens
from ..replay import load_arms
from ..stats import cohen_kappa, wilson


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def report(items: list[dict], runs: list[dict], arms: dict, labels=DEFAULT_LABELS,
           reference_arm: str | None = None) -> tuple[str, dict]:
    runs = [r for r in runs if r.get("label")]
    ids = {it["id"] for it in items}
    runs = [r for r in runs if r["id"] in ids]
    kind_of = {it["id"]: it.get("kind", "all") for it in items}

    # reference label per item
    if reference_arm:
        ref = {}
        for r in runs:
            if r["arm"] == reference_arm and r["rep"] == 0:
                ref[r["id"]] = r["label"]
        ref_name = f"arm '{reference_arm}' rep 0"
    else:
        ref = {it["id"]: it.get("reference") for it in items if it.get("reference")}
        ref_name = "item reference (live label)"

    by = defaultdict(list)
    for r in runs:
        by[(kind_of[r["id"]], r["arm"])].append(r)

    L, out = [], {}
    p = L.append
    p(f"consistency report: {len(runs)} labelled runs over {len({r['id'] for r in runs})} items")
    p(f"reference = {ref_name}\n")
    for kind in sorted({k for k, _ in by}):
        rl = Counter(ref[i] for i in ref if kind_of.get(i) == kind)
        p(f"== {kind} ==  reference mix: " + " ".join(f"{l}={rl[l]}" for l in labels))
        p(f"{'arm':<16}{'n':>4} " + "".join(f"{l[:5]:>6}" for l in labels)
          + f"{'agree':>7} {'95% CI':>11}{'kappa':>7}{'fmt':>6}{'tok':>8}{'lat_s':>7}")
        for name in arms:
            rs = by.get((kind, name), [])
            if not rs:
                continue
            c = Counter(r["label"] for r in rs)
            # the reference arm's own rep 0 IS the reference: exclude it
            pairs = [(ref[r["id"]], r["label"]) for r in rs if r["id"] in ref
                     and not (name == reference_arm and r["rep"] == 0)]
            k = sum(a == b for a, b in pairs)
            lo, hi = wilson(k, len(pairs))
            kp = cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])
            fmt = sum(is_compliant(r.get("raw", ""), labels) for r in rs) / len(rs)
            tok = _median([total_tokens(r.get("usage")) for r in rs if r.get("usage")])
            lat = _median([r.get("latency_ms", 0) for r in rs]) / 1000
            agree = k / len(pairs) if pairs else float("nan")
            p(f"{name:<16}{len(rs):>4} " + "".join(f"{c[l]:>6}" for l in labels)
              + f"{agree:>7.0%} [{lo:>4.0%},{hi:>4.0%}]{kp:>7.2f}{fmt:>6.0%}{tok:>8,}{lat:>7.1f}")
            out[f"{kind}/{name}"] = dict(n=len(rs), mix=dict(c), agree=agree, ci=[lo, hi],
                                         kappa=kp, fmt_ok=fmt, tokens=tok, latency_s=lat)
        # repeat stability per arm with reps >= 2
        for name, arm in arms.items():
            if arm["reps"] < 2:
                continue
            per = defaultdict(list)
            for r in by.get((kind, name), []):
                per[r["id"]].append(r["label"])
            full = {i: v for i, v in per.items() if len(v) >= arm["reps"]}
            if full:
                st = sum(len(set(v + ([ref[i]] if i in ref else []))) == 1 for i, v in full.items())
                lo, hi = wilson(st, len(full))
                p(f"repeat stability [{name}] (reference + {arm['reps']} reps identical): "
                  f"{st}/{len(full)} = {st / len(full):.0%} [{lo:.0%},{hi:.0%}]")
                out[f"{kind}/{name}/repeat_stable"] = st / len(full)
        # order effect: shuffle arm vs its orig twin (same model, mode)
        for name, arm in arms.items():
            if arm["transform"] != "shuffle":
                continue
            twin = next((n for n, a in arms.items() if a["transform"] == "orig"
                         and a["model"] == arm["model"] and a["mode"] == arm["mode"]), None)
            if not twin:
                continue
            fr = {}
            for n in (name, twin):
                pairs = [(ref[r["id"]], r["label"]) for r in by.get((kind, n), []) if r["id"] in ref]
                if pairs:
                    fr[n] = sum(a != b for a, b in pairs) / len(pairs)
            if len(fr) == 2:
                p(f"order effect [{name} vs {twin}]: flips {fr[name]:.0%} vs {fr[twin]:.0%} "
                  f"-> excess {fr[name] - fr[twin]:+.0%}")
                out[f"{kind}/{name}/order_excess"] = fr[name] - fr[twin]
        p("")
    return "\n".join(L), out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Consistency report for replayed judgement calls")
    ap.add_argument("--items", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--arms", required=True)
    ap.add_argument("--reference-arm")
    ap.add_argument("--out", help="write the text report here (and .json beside it)")
    a = ap.parse_args(argv)
    run_cfg, arms = load_arms(a.arms)
    labels = tuple(run_cfg.get("labels", DEFAULT_LABELS))
    txt, summary = report(load(a.items), load(a.runs), arms, labels, a.reference_arm)
    print(txt)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
