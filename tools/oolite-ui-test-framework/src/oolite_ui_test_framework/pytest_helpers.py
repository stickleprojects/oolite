"""Helpers for writing game tests: enforce() turns an (outcome, reason) check result into pytest pass / fail / skip."""
import pytest

from . import pass_fail


def enforce(result):
    outcome, reason = result
    if outcome == pass_fail.FAILED: pytest.fail(reason, pytrace=False)
    if outcome == pass_fail.SKIPPED: pytest.skip(reason)
