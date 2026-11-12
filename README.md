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

> Status: work in progress. Core harness, consistency eval and the public GDELT
> headline source are done; outcome evals and the full write-up are next.

## Early findings from the case study

| Finding | Evidence |
|---|---|
| `claude -p` carries ~26K tokens of hidden context per call; trimming it costs ~40x less and **does not change the verdicts** | 7-token prompt: 25.9K -> 0.6K input tokens. Trimmed vs full: 95% / 92% agreement (equity / gold), the same as re-asking in full mode |
| A cheaper model is not a drop-in replacement | Haiku labelled 13/20 equity sessions NEUTRAL vs 5/20 for the production model (60% agreement) |
| Order sensitivity depends on the domain | Shuffling headlines: +0% extra flips on equity, +18% on gold |
| Re-asking adds noise, not signal | Hourly re-calls flipped ~20% of the time with no predictive value; the first call of the session carried the signal |
| The headline *source* matters | Same model + prompt on public GDELT headlines instead of the production feed: 80% agreement on equity, 65% on gold |

Sample sizes are small (20 sessions per market) and are reported with 95% intervals in `findings/`.

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
lje/sources/gdelt.py    public headlines from GDELT 2.0 bulk files
lje/stats.py            Wilson CI, Cohen's kappa, permutation test, bootstrap
configs/                arms + prompt templates
examples/demo/          build items from GDELT
findings/               write-ups with numbers
```

## License

MIT
