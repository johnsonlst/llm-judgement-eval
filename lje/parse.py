"""Turn a free-text model reply into one label.

Rule (battle-tested on a live trading bot): models occasionally emit a false
start and self-correct ("BEARISH\\nWait, let me reconsider...\\nBULLISH\\n..."),
so the LAST line that is a bare label wins, and the next non-empty line is the
reason. If no line is a bare label, fall back to searching the first line.
"""
import re

DEFAULT_LABELS = ("bullish", "bearish", "neutral")


def _label_re(labels):
    alt = "|".join(re.escape(l) for l in labels)
    return re.compile(rf"[*#\s]*({alt})[*:.\s]*", re.IGNORECASE)


def parse_label(text: str, labels=DEFAULT_LABELS, default: str | None = None) -> tuple[str | None, str]:
    """Return (label, reason). label is lower-case, or `default` if none found.

    The fallback default is None (unparsed) rather than a real label, so
    parse failures are counted instead of silently becoming e.g. "neutral".
    """
    lines = [l.strip() for l in (text or "").strip().split("\n")]
    rx = _label_re(labels)
    idx = None
    for i, line in enumerate(lines):
        if rx.fullmatch(line):
            idx = i
    if idx is not None:
        label = rx.fullmatch(lines[idx]).group(1).lower()
        reason = next((l for l in lines[idx + 1:] if l), "")
        return label, reason
    first = lines[0] if lines else ""
    for l in labels:
        if re.search(rf"\b{re.escape(l)}\b", first, re.IGNORECASE):
            return l.lower(), next((x for x in lines[1:] if x), "")
    return default, next((x for x in lines[1:] if x), "")


def is_compliant(text: str, labels=DEFAULT_LABELS) -> bool:
    """First non-empty line is a bare label (the format the prompt asks for)."""
    first = next((l.strip() for l in (text or "").split("\n") if l.strip()), "")
    return bool(_label_re(labels).fullmatch(first))
