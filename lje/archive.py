"""Archive every live LLM call so it can be replayed and scored later.

Drop-in pattern for a production system:

    from lje.archive import Archiver
    arc = Archiver("data/calls.jsonl")
    label, reason = arc.record(kind="equity", prompt=prompt, model=model,
                               call=lambda: provider(prompt, model),
                               parse=parse_label,
                               inputs={"headlines": headlines})

The archive line is the contract the replay runner reads:
  ts_utc, kind, model, mode, prompt_hash, prompt, inputs, raw, label, reason,
  latency_ms, usage, error
Writing never raises: an archive failure must not take down the live system.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class Archiver:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, rec: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:                      # never break the caller
            log.warning("archive write failed: %s", e)

    def record(self, *, kind: str, prompt: str, model: str, call, parse,
               template: str | None = None, inputs: dict | None = None):
        """Run `call()` (-> provider dict), archive it, return (label, reason).

        Re-raises nothing from the provider: a provider error is archived and
        returned as (None, error text) so the caller decides the fallback.
        """
        rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "kind": kind,
               "model": model,
               "prompt_hash": hashlib.sha1((template or prompt).encode("utf-8")).hexdigest()[:8],
               "prompt": prompt, "inputs": inputs or {}}
        out = call()
        rec.update({k: out.get(k) for k in ("mode", "raw", "latency_ms", "usage", "error")})
        if out.get("error"):
            self.write(rec)
            return None, out["error"]
        rec["label"], rec["reason"] = parse(out.get("raw", ""))
        self.write(rec)
        return rec["label"], rec["reason"]


def load(path: str | Path) -> list[dict]:
    """Read an archive / items file (JSONL). Splits on '\\n' only: str.splitlines()
    would also split on U+2028 etc., which occur inside real headlines."""
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(l) for l in text.split("\n") if l.strip()]
