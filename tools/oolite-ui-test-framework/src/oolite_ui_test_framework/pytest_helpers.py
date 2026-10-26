"""Helpers for writing game tests: enforce() turns an (outcome, reason) check result into pytest pass / fail / skip."""
import pytest

from . import outcomes


def enforce(result):
    outcome, reason = result
    if outcome == outcomes.FAILED: pytest.fail(reason, pytrace=False)
    if outcome == outcomes.SKIPPED: pytest.skip(reason)
