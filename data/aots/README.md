# AOTS case-study dataset

These are the labels a live options-trading bot ("AOTS") got from Claude, with the market returns that followed. The data runs from 2026-03-27 to 2026-11-11.

Before each US session, and hourly while the market is open, the bot asks Claude for a BULLISH / BEARISH / NEUTRAL read on recent headlines. There are two kinds of call:

- `equity`: market headlines, scored on QQQ, SPY and IWM.
- `gold`: gold-price headlines, scored on GLD.

## What is (and is not) here

The files contain only the labels and the returns that followed them. The following are deliberately left out:

- headline text and the model's reasons
- the bot's trading rules and how it uses the label
- trades, P&L and account data

`model` is `cli-default` before 2026-10-16. Until then the bot called `claude -p` without `--model`, so the CLI's default model answered. From 2026-10-16 the model is pinned to `claude-opus-5-5`.

## sessions.csv: one label per session

The first call of each US trading day: about 09:15 ET, before the open. Rows whose first call came after 10:30 ET are dropped.

| column | meaning |
|---|---|
| `date` | US trading date |
| `kind` | `equity` or `gold` |
| `symbol` | ETF the label is scored on |
| `label` | `bullish` / `bearish` / `neutral` |
| `model` | see above |
| `call_et` | time of the call, US Eastern (about 90% fall between 09:15 and 09:29) |
| `r_close` | that day's open to close |
| `r_1d` | that day's open to the next session's close |
| `r_5d` | that day's open to the close 4 sessions later |
| `prev_1d` | prior close-to-close return (known before the call; momentum baseline) |

## calls.csv: every call made while the market was open

QQQ for equity, GLD for gold. Returns start from the first hourly bar that opens at or after the call.

| column | meaning |
|---|---|
| `is_first` | 1 for the first call of the session |
| `flip` | 1 if the label differs from the previous call that session |
| `r_1h` | return over that hourly bar |
| `r_close` | return from that bar's open to the session close |

## Reproduce

```bash
python -m lje.evals.outcome --rows data/aots/sessions.csv
python -m lje.evals.outcome --rows data/aots/calls.csv --group date --horizons r_1h,r_close --where flip=1
```

The calls file needs `--group date`: calls on the same day are not independent, so confidence intervals resample whole days.

Prices come from Yahoo Finance via `yfinance` (unadjusted open and close).
