# 02: Cheaper models and headline order

## Question

1. Could a cheaper, faster model make the same call?
2. Does the verdict depend on the order the headlines are listed in?

## Setup

All replays are trimmed (see [01](01-trimmed-context.md)) and use the same 20 first-of-session prompts per market as in 01. The reference is the live label.

- **Model swap:** Sonnet and Haiku instead of Opus.
- **Order:** Opus with the headline list shuffled by a fixed seed per item. The order effect is the shuffled arm's flip rate minus the plain re-ask's flip rate.

## Results

| arm | equity agree | kappa | gold agree | kappa |
|---|---|---|---|---|
| Opus (re-ask) | 95% [83, 99] | 0.90 | 92% [80, 97] | 0.72 |
| Opus, shuffled | 95% [76, 99] | 0.90 | 75% [53, 89] | 0.35 |
| Sonnet | 85% [64, 95] | 0.72 | 75% [53, 89] | 0.28 |
| Haiku | 60% [39, 78] | 0.37 | 65% [43, 82] | 0.10 |

Label mix on equity (bullish / neutral / bearish): live 2/5/13, Opus 6/8/26 over 2 reps, Sonnet 1/8/11, **Haiku 1/13/6**.

Order effect (shuffled flips minus re-ask flips): equity **+0%**, gold **+18%**.

## Reading

- **Haiku is not a drop-in replacement.** It does not just add noise: it leans NEUTRAL, labelling 13 of 20 equity sessions NEUTRAL where the live model said NEUTRAL in 5. A downstream system that treats NEUTRAL as "no objection" would quietly lose its filter.
- Sonnet is closer, but its kappa (0.72 equity, 0.28 gold) is still well below Opus re-asking itself.
- **Gold is order-sensitive and equity is not.** Gold headlines are fewer and more mixed (central-bank buying vs yields vs the dollar). When the evidence is balanced, what comes first tips it. This is a property of the input, not just of the model.
- A cheap way to tell a stable label from a fragile one: ask twice with shuffled order. If the two answers disagree, the label is fragile and should get less weight.

## Caveats

n=20 per market, one prompt template per market, one time period.
