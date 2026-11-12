# Findings

This is a case study of a live trading bot that asks Claude for a BULLISH / BEARISH / NEUTRAL read on market headlines before each US session. It covers 2026-03-27 to 2026-11-11.

| # | Question | Short answer |
|---|---|---|
| [01](01-trimmed-context.md) | Does stripping `claude -p`'s hidden context change the verdicts? | No. It uses ~40x fewer input tokens, and the verdicts agree 92-95% of the time, close to how often a re-ask agrees. |
| [02](02-models-and-order.md) | Can a cheaper model do the job? Does headline order matter? | Not at this quality: Haiku agrees 60-65%. Order matters for gold but not equity. |
| [03](03-source-sensitivity.md) | Does the result survive swapping the headline feed for a public one? | Partly: 80% agreement on equity, 65% on gold. |
| [04](04-outcomes.md) | Did the verdicts predict returns? | A small edge on QQQ the same day, which does not survive a multiple-testing correction. Nothing at longer horizons, and nothing on gold. |

How to read the numbers:

- **Agreement** is the share of sessions where two setups gave the same label, with a 95% Wilson interval.
- **Kappa** is agreement corrected for chance: 1 is perfect, 0 is no better than guessing from the label mix.
- **Signed return** is what you would earn by following the label: long on BULLISH, short on BEARISH, out on NEUTRAL. The numbers are in basis points (1bp = 0.01%) and come with bootstrap intervals.

Every sample here is small (20 sessions for the replay studies, 98-120 labelled sessions for outcomes). Read the intervals, not just the point estimates.
