# 03: Does the headline source matter?

## Question

The production headline feed can't be published. If the same model and prompt read *public* headlines (from GDELT) for the same sessions, how often does it reach the same verdict?

## Setup

For each first-of-session call, the prompt was rebuilt with the bot's own template. The headlines came from GDELT 2.0 bulk files covering the same lookback window, using the source filters in `lje/sources/gdelt.py`:

- **equity:** an allowlist of financial news sites.
- **gold:** price-wording regex plus a denylist, because the raw GDELT "gold" stream is full of medals and mining juniors.

Each rebuilt prompt was run on trimmed Opus and scored against the live label. Sessions with fewer than 10 usable headlines were dropped, which removed 3 gold sessions.

The ceiling is Opus re-asked on the bot's own headlines: 95% equity and 92% gold (see 01).

## Results

| market | n | agree | kappa | headlines per prompt (median) |
|---|---|---|---|---|
| equity | 20 | 80% [58, 92] | 0.60 | 45 |
| gold | 17 | 65% [41, 83] | 0.20 | 20 |

Equity label mix: live 2/5/13 (bull/neutral/bear), GDELT 1/6/13. The mix is almost identical, but **both live BULLISH sessions became NEUTRAL** on GDELT.

## Reading

- On equity, public headlines reproduce the general tone but not the rare calls. The BULLISH days are the ones that matter most for prediction ([04](04-outcomes.md)), and they are the ones the public source loses.
- On gold, swapping the source moves the verdict about as much as swapping the model to Haiku. Together with gold's order sensitivity in 02, the gold label depends heavily on which headlines happen to be in the window.
- **Practical rule:** treat the headline source as part of the model. A label validated on one feed is not validated on another.
- The public demo (`examples/demo`) is equity-only for this reason.

## Caveats

- The GDELT title extraction and domain filters are heuristics.
- n is small, and the gold sample is smaller (17) because of the dropped sessions.
