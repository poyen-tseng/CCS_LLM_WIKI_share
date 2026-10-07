"""Replay every fixture with jev_mode="always" against the live Jev API (needs TYPESAFE_API_KEY).

Jev's answer must be at least as good as the rules: overall accuracy >= 0.9 (the JEV_ACCELERATION.md
target) and the Jev-only case (C10, free-text expectation) must be solved.
"""
import os

import pytest

from jev_accel import replay, tools

pytestmark = [pytest.mark.jev,
              pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="TYPESAFE_API_KEY not set")]


@pytest.fixture(scope="module")
def summary():
    tools._gate = None
    return replay.run("always", save=True)


def test_jev_was_reachable(summary):
    assert "jev_errors" not in summary, summary.get("jev_errors")


def test_overall_accuracy(summary):
    s = summary["by_bridge"]
    acc = sum(b["correct"] for b in s.values()) / sum(b["cases"] for b in s.values())
    assert acc >= 0.9, replay.markdown(summary)


def test_jev_only_case_is_solved(summary):
    assert not [m for m in summary["misses"] if m["needs_jev"]], replay.markdown(summary)
