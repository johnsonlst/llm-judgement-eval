# 04: Did the verdicts predict returns?

## Question

Agreement and stability only show that the label is *repeatable*. Did following it make money, compared with baselines that read no headlines at all?

## Setup

The data is [`data/aots/sessions.csv`](../data/aots/sessions.csv): the first call of each US session from 2026-03-27 to 2026-11-11.

- 158 equity sessions, scored on QQQ, SPY and IWM.
- 126 gold sessions, scored on GLD.
- About 90% of first calls were made at 09:15-09:29 ET, before the open, so returns measured from the open contain nothing the model could have seen.

Signals compared:

- **label**: long on BULLISH, short on BEARISH, out on NEUTRAL.
- **always_long**: long every session (the market's drift).
- **momentum**: the sign of the previous session's return.

Each signal gets a signed return in bp, a bootstrap 95% CI and a two-sided permutation p.

```bash
python -m lje.evals.outcome --rows data/aots/sessions.csv
```

## Results: same day (open to close)

| symbol | label n | label signed bp | 95% CI | hit | perm p | always_long | momentum |
|---|---|---|---|---|---|---|---|
| QQQ | 120 | **+21.3** | [+5.2, +38.3] | 59% | **0.009** | +2.3 | +15.7 |
| SPY | 120 | +9.5 | [-0.4, +19.8] | 58% | 0.057 | +1.1 | +1.9 |
| IWM | 120 | +3.7 | [-10.9, +18.5] | 56% | 0.59 | -4.3 | -7.9 |
| GLD | 98 | +6.5 | [-9.6, +22.6] | 52% | 0.39 | -7.4 | -8.4 |

Keeping only calls made before 09:30 ET leaves QQQ unchanged: +21.3bp [+4.7, +37.7], p=0.011, n=115.

Mean QQQ open-to-close return by label: BULLISH **+48.6bp** (70% up days), BEARISH -10.9bp, NEUTRAL -7.6bp.

## Results: longer horizons

No label signal is distinguishable from zero at the next-day (`r_1d`) or 5-day (`r_5d`) horizon, on any symbol. At 5 days, `always_long` beats the label on every equity ETF, e.g. SPY +39.4bp [+11.3, +66.6] vs label +1.8bp.

## Results: re-asking during the session

The bot re-asks every hour, and the data is in [`data/aots/calls.csv`](../data/aots/calls.csv). Calls on the same day are not independent, so the CIs resample whole days (`--group date`).

| QQQ, signed bp | n | next hour | to close |
|---|---|---|---|
| first call of session | 120 | +3.3 [-6.6, +13.5] | **+20.7 [+5.5, +37.0]** |
| re-ask, same label | 570 | +2.8 [-0.0, +5.6] | +14.2 [+6.3, +22.3] |
| re-ask, **flipped** label | 99 | +2.1 [-3.5, +8.0] | +5.5 [-3.5, +15.9] |

On GLD, flipped re-asks did predict the next hour slightly: +8.5bp [+3.7, +14.0], n=57. Nothing else on gold separates from zero.

## Reading

- **The only notable result is the same-day QQQ signal**: about +21bp per labelled session, mostly from the BULLISH days. That is suggestive and not proven. This page runs 12 label tests (4 symbols x 3 horizons). With a Bonferroni correction, the bar is p < 0.004, and 0.009 does not clear it. SPY points the same way, which is weak support, but SPY and QQQ are highly correlated, so it is not independent evidence.
- **The edge is short-lived.** It shows up in the same session and is gone by the next close. That is what you'd expect if the headlines reflect information the market is still absorbing that morning, not a lasting view.
- **The model calls BEARISH far more often than the market fell.** 87 of 158 equity sessions were labelled BEARISH, yet QQQ rose on 51% of all sessions. The bearish label carried little information (QQQ averaged -10.9bp on BEARISH days, about the same as NEUTRAL days). The useful information was in the rare BULLISH calls, which are also the calls a public headline feed fails to reproduce ([03](03-source-sensitivity.md)).
- **Hourly re-asks:** on equity, a flipped label added nothing; the information was already in the first call. Gold's flipped re-asks showed a small one-hour effect on 57 calls, which needs more data before anyone acts on it.
- **Gold:** no evidence the session label predicts GLD.

## Caveats

- One period (Mar-Nov 2026), one bot, one prompt template per market.
- The model was the CLI default until 2026-10-16 and pinned Opus after that, so this is not a clean single-model test.
- Returns are gross, unadjusted ETF prices, and following the label is not the bot's actual trade. This page measures information, not trading P&L.
