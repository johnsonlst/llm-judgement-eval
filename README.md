# llm-judgement-eval

**Can you trust an LLM's judgement call inside an automated system?**

A small, dependency-free harness to answer that with evidence instead of vibes:

1. **Archive** every live call: prompt, inputs, raw reply, label, model, latency, tokens.
2. **Replay** archived prompts under controlled *arms*: different models, re-asks,
   shuffled input order, trimmed vs full provider context.
3. **Score** the judgement: consistency (repeat stability, agreement, kappa, order
   sensitivity), cost (tokens, latency), and outcomes (did the call predict anything?).

The case study is a live options-trading bot that asks Claude for a
BULLISH / BEARISH / NEUTRAL read of market headlines before each session.
The harness is generic: any system that turns text into a label can use it.

> Status: harness, consistency and outcome evals, the public GDELT source and a
> derived dataset from the live system are done. Write-ups are in [`findings/`](findings/).

## Early findings from the case study

| Finding | Evidence |
|---|---|
| `claude -p` carries ~26K tokens of hidden context per call; trimming it costs ~40x less with **no detectable change in verdicts** | 7-token prompt: 25.9K -> 0.6K input tokens. Trimmed vs live: 95% / 92% agreement (equity / gold), kappa 0.90 / 0.72 |
| A cheaper model is not a drop-in replacement | Haiku labelled 13/20 equity sessions NEUTRAL vs 5/20 for the production model (60% agreement) |
| Order sensitivity depends on the domain | Shuffling headlines: +0% extra flips on equity, +18% on gold |
| The verdict carried a small, short-lived edge on one market | QQQ open-to-close +21bp per labelled session [+5, +38], p=0.009, which misses a 12-test Bonferroni bar; gone by the next close; nothing on gold |
| Re-asking mid-session added little on equity | Flipped hourly labels on QQQ: +5bp to close [-4, +16] vs +21bp for the first call of the session |
| The headline *source* matters | Same model + prompt on public GDELT headlines instead of the production feed: 80% agreement on equity, 65% on gold |

Sample sizes are small (20 sessions per market for replays, ~120 labelled sessions for outcomes) and are reported with 95% intervals in [`findings/`](findings/).

## Quickstart

```bash
pip install -e ".[dev]"            # stdlib only at runtime; pytest for tests
pytest -q

# 1. public headlines -> replayable items (one per US trading day)
python -m lje.sources.gdelt --start 2026-10-12 --end 2026-11-11     # prefetch, ~4 min
python examples/demo/make_items.py --start 2026-10-15 --end 2026-11-11 --out out/demo_items.jsonl

# 2. replay under the arms in configs/arms.toml (resumable)
python -m lje.replay --items out/demo_items.jsonl --arms configs/arms.toml --out out/demo_runs.jsonl

# 3. consistency report
python -m lje.evals.consistency --items out/demo_items.jsonl --runs out/demo_runs.jsonl \
    --arms configs/arms.toml --reference-arm opus

# 4. outcomes on the case-study dataset (no API calls)
python -m lje.evals.outcome --rows data/aots/sessions.csv
```

Requires the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) (`claude -p`) signed in.

## Layout

```
lje/archive.py          archive pattern for a live system (never breaks the caller)
lje/replay.py           resumable replay runner over arms
lje/parse.py            reply -> label (last bare label wins; unparsed is counted, not guessed)
lje/transforms.py       arm transforms (identity, seeded list shuffle)
lje/providers/          claude_cli (full / trim modes, token accounting)
lje/evals/consistency.py agreement, kappa, repeat stability, order effect, cost
lje/evals/outcome.py    signed returns vs no-text baselines, bootstrap + permutation
lje/sources/prices.py   daily prices (yfinance, optional) -> per-session returns
lje/sources/gdelt.py    public headlines from GDELT 2.0 bulk files
lje/stats.py            Wilson CI, Cohen's kappa, permutation test, (block) bootstrap
data/aots/              derived case-study dataset: labels + returns, no text
configs/                arms + prompt templates
examples/demo/          build items from GDELT
findings/               write-ups with numbers
```

## License

MIT
