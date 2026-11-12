"""Provider: the Claude Code CLI in print mode (`claude -p`).

Two modes:
  full  what you get by default: the full Claude Code system prompt, tool
        definitions and any CLAUDE.md/settings in the working directory.
        Measured at ~26K input tokens of overhead for a 7-token prompt.
  trim  --system-prompt <short> --tools "" --strict-mcp-config
        --setting-sources ""  -> ~0.6K overhead (~40x less). On a live
        sentiment classifier the trimmed calls agreed with full-mode verdicts
        92-95% of the time, the same as re-asking in full mode.

The prompt is passed after "--" so a variadic flag (--tools) cannot swallow it.
Returns a dict; never raises for model/CLI errors (they go in "error").
"""
import json
import subprocess
import time

TRIM_SYSTEM = "You are a careful classifier. Follow the instructions in the user's message exactly."


def build_cmd(model: str, mode: str = "trim", system: str | None = None) -> list[str]:
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence",
           "--output-format", "json"]
    if mode == "trim":
        cmd += ["--system-prompt", system or TRIM_SYSTEM, "--tools", "",
                "--strict-mcp-config", "--setting-sources", ""]
    elif mode != "full":
        raise ValueError(f"unknown mode {mode!r} (use 'trim' or 'full')")
    return cmd


def call(prompt: str, model: str, mode: str = "trim", system: str | None = None,
         timeout: int = 120, cwd: str | None = None) -> dict:
    rec = {"provider": "claude_cli", "model": model, "mode": mode}
    t0 = time.monotonic()
    try:
        res = subprocess.run(build_cmd(model, mode, system) + ["--", prompt], cwd=cwd,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout)
    except Exception as e:
        rec.update(latency_ms=int((time.monotonic() - t0) * 1000), error=repr(e))
        return rec
    rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
    rec["returncode"] = res.returncode
    try:
        d = json.loads(res.stdout)
    except json.JSONDecodeError:
        rec.update(raw=res.stdout, error="non-JSON output", stderr=res.stderr[-2000:])
        return rec
    rec["raw"] = d.get("result") or ""
    u = d.get("usage") or {}
    rec["usage"] = {k: u.get(k) for k in ("input_tokens", "cache_creation_input_tokens",
                                          "cache_read_input_tokens", "output_tokens")}
    if d.get("is_error") or res.returncode != 0:
        rec.update(error="cli error", stderr=(rec["raw"] + "\n" + res.stderr)[-2000:])
    return rec


def total_tokens(usage: dict | None) -> int:
    return sum(v or 0 for v in (usage or {}).values())
