# 01: Trimming `claude -p`'s hidden context

## Question

The bot calls the Claude Code CLI (`claude -p`) for every judgement. By default, the CLI loads its own system prompt, tool definitions, MCP servers and project settings before it reads the prompt. Does that context change the verdict, or does it only cost tokens?

## Setup

- **full**: `claude -p <prompt>`, which is how the bot ran in production.
- **trim**: `claude -p --system-prompt <one line> --tools "" --strict-mcp-config --setting-sources "" -- <prompt>`.

Each of the two setups was replayed on the exact first-of-session prompts the bot archived: 20 equity and 20 gold sessions with Opus. The reference was the label the bot actually got live.

## Results

| | input tokens per call |
|---|---|
| 7-token test prompt, full | ~25,900 |
| 7-token test prompt, trim | ~600 |
| real sentiment prompt, trim | ~3,050 (median) |

| market | trim vs live label | kappa | trim repeat-stable* | full re-ask vs live |
|---|---|---|---|---|
| equity | 95% [83, 99] (n=40) | 0.90 | 19/20 = 95% | 100% [78, 100] (n=14) |
| gold | 92% [80, 97] (n=40) | 0.72 | 18/20 = 90% | 100% [76, 100] (n=12) |

\* The live label plus 2 trimmed re-asks are all identical.

## Reading

- Trimming cuts the overhead by about 40x on a tiny prompt, and real prompts are about 9x cheaper end to end (~3K vs ~28K input tokens).
- The trimmed verdict matches the live one 92-95% of the time. Re-asking the *full* setup agreed 100% of the time, on a smaller sample whose intervals overlap the trimmed ones. With n=20 per market, I can't tell the difference between "trim changes nothing" and "trim changes about 1 verdict in 20".
- **Decision:** the production bot switched to trimmed calls on 2026-11-12 and can switch back with one flag. Future outcome data will tell whether anything moved.

## Caveats

- Same model (Opus), two markets, 20 sessions each.
- The full-mode replay ran on fewer sessions because it uses more quota.
