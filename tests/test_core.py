import json

import pytest

from lje.archive import Archiver, load
from lje.parse import is_compliant, parse_label
from lje.providers.claude_cli import build_cmd
from lje.replay import load_arms, seed_for
from lje.sources import gdelt
from lje.stats import cohen_kappa, perm_test_mean, wilson
from lje.transforms import shuffle_list


# --- parse -------------------------------------------------------------------
def test_parse_simple():
    assert parse_label("BEARISH\nRates up.") == ("bearish", "Rates up.")


def test_parse_last_bare_label_wins():
    txt = "BEARISH\nWait, let me reconsider.\nBULLISH\nEarnings beat."
    assert parse_label(txt) == ("bullish", "Earnings beat.")


def test_parse_markdown_and_fallback():
    assert parse_label("**Neutral**\nmixed")[0] == "neutral"
    assert parse_label("Overall bullish tone.\nreason")[0] == "bullish"
    assert parse_label("I cannot tell.")[0] is None          # unparsed, not silently neutral


def test_compliance():
    assert is_compliant("BULLISH\nx")
    assert not is_compliant("The sentiment is BULLISH")


# --- stats -------------------------------------------------------------------
def test_wilson_bounds():
    lo, hi = wilson(16, 20)
    assert 0.5 < lo < 0.8 < hi < 1.0


def test_kappa():
    a = ["x", "y", "x", "y"]
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    assert cohen_kappa(a, ["y", "x", "y", "x"]) == pytest.approx(-1.0)


def test_perm_test_detects_signal():
    sig = [1, -1] * 30
    ret = [0.01, -0.01] * 30
    mean, p = perm_test_mean(sig, ret, n_perm=2000)
    assert mean > 0 and p < 0.01


# --- transforms ----------------------------------------------------------------
def test_shuffle_only_moves_list_lines():
    prompt = "intro\n- a\n- b\n- c\n- d\noutro"
    out = shuffle_list(prompt, seed=1)
    assert out != prompt
    assert out.split("\n")[0] == "intro" and out.split("\n")[-1] == "outro"
    assert sorted(out.split("\n")[1:5]) == ["- a", "- b", "- c", "- d"]
    assert shuffle_list(prompt, 1) == out                     # reproducible


def test_seed_is_stable():
    assert seed_for("equity-20261111", 0) == seed_for("equity-20261111", 0)
    assert seed_for("equity-20261111", 0) != seed_for("equity-20261111", 1)


# --- provider ------------------------------------------------------------------
def test_trim_cmd_has_flags():
    cmd = build_cmd("claude-haiku-5-5", "trim")
    for flag in ("--system-prompt", "--tools", "--strict-mcp-config", "--setting-sources"):
        assert flag in cmd
    assert "--tools" not in build_cmd("m", "full")
    with pytest.raises(ValueError):
        build_cmd("m", "bogus")


# --- archive / config ----------------------------------------------------------
def test_archiver_roundtrip(tmp_path):
    arc = Archiver(tmp_path / "a.jsonl")
    fake = lambda: {"mode": "trim", "raw": "BULLISH\nok", "latency_ms": 5, "usage": {}}
    assert arc.record(kind="equity", prompt="p", model="m", call=fake, parse=parse_label) == ("bullish", "ok")
    err = lambda: {"mode": "trim", "error": "boom"}
    assert arc.record(kind="equity", prompt="p", model="m", call=err, parse=parse_label) == (None, "boom")
    rows = load(tmp_path / "a.jsonl")
    assert [r.get("label") for r in rows] == ["bullish", None]


def test_load_survives_unicode_line_separator(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(json.dumps({"t": "a b"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert load(p) == [{"t": "a b"}]


def test_arms_config(tmp_path):
    p = tmp_path / "arms.toml"
    p.write_text('[arms.a]\nmodel="m"\nreps=2\n[arms.b]\nmodel="m"\ntransform="shuffle"\n')
    _, arms = load_arms(p)
    assert arms["a"]["reps"] == 2 and arms["b"]["transform"] == "shuffle"
    p.write_text('[arms.c]\nmodel="m"\ntransform="nope"\n')
    with pytest.raises(ValueError):
        load_arms(p)


# --- gdelt ---------------------------------------------------------------------
def test_gdelt_policy():
    assert gdelt._allowed("cnbc.com", "equity")
    assert gdelt._allowed("markets.businessinsider.com", "equity")
    assert not gdelt._allowed("tickerreport.com", "equity")
    assert gdelt._allowed("some-local-paper.com", "gold")
    assert not gdelt._allowed("tickerreport.com", "gold")


def test_gdelt_keywords():
    eq, au = gdelt.KEYWORDS["equity"], gdelt.KEYWORDS["gold"]
    assert eq.search("Stocks slide as Fed signals rate hike")
    assert not eq.search("Local bakery opens second shop")
    assert au.search("Gold prices climb on softer dollar")
    assert not au.search("Swimmer wins gold in 200m")          # medals are not gold news


def test_gdelt_slots_align():
    from datetime import datetime, timezone
    s = datetime(2026, 11, 1, 1, 30, tzinfo=timezone.utc)
    e = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
    assert [t.hour for t in gdelt.slots(s, e, 2)] == [2, 4, 6, 8]


# --- outcome -----------------------------------------------------------------
from lje.evals.outcome import report as outcome_report  # noqa: E402
from lje.sources.prices import attach, session_returns  # noqa: E402
from lje.stats import block_bootstrap_ci  # noqa: E402


BARS = [("2026-01-02", 100, 101), ("2026-01-05", 101, 99), ("2026-01-06", 99, 102),
        ("2026-01-07", 102, 103), ("2026-01-08", 103, 104), ("2026-01-09", 104, 100)]


def test_session_returns_from_open():
    r = session_returns(BARS, "2026-01-06")
    assert r["r_close"] == pytest.approx(102 / 99 - 1)
    assert r["r_1d"] == pytest.approx(103 / 99 - 1)
    assert r["r_5d"] is None                                  # not enough bars yet
    assert r["prev_1d"] == pytest.approx(99 / 101 - 1)      # known before the open
    assert session_returns(BARS, "2026-01-03") is None       # not a trading day


def test_attach_one_row_per_symbol():
    labels = [{"date": "2026-01-06", "kind": "equity", "label": "bullish"}]
    rows = attach(labels, {"QQQ": BARS, "SPY": BARS}, {"equity": ["QQQ", "SPY"]})
    assert [r["symbol"] for r in rows] == ["QQQ", "SPY"]


def test_outcome_signs_and_baselines():
    rows = [{"kind": "k", "symbol": "X", "label": l, "r_close": r, "prev_1d": 0.01}
            for l, r in [("bullish", 0.01), ("bearish", -0.02), ("neutral", 0.05)]]
    _, out = outcome_report(rows, ["r_close"], n_boot=200)
    lab = out["k/X"]["r_close/label"]
    assert lab["n"] == 2 and lab["signed_bp"] == pytest.approx(150)   # (+1% + 2%) / 2
    assert lab["hit"] == 1.0
    assert out["k/X"]["r_close/always_long"]["perm_p"] is None        # constant signal


def test_block_bootstrap_resamples_groups():
    lo, hi = block_bootstrap_ci([1.0, 1.0, 3.0, 3.0], ["a", "a", "b", "b"], n_boot=500)
    assert 1.0 <= lo <= hi <= 3.0
    assert block_bootstrap_ci([], []) != block_bootstrap_ci([], [])   # nan != nan
