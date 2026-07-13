"""Tests for reviewed Grype exception policy."""

from __future__ import annotations

from datetime import date

from scripts.ci.validate_grype_exceptions import validate


def test_grype_exception_validator_passes_for_current_entries() -> None:
    assert validate(today=date(2026, 7, 13)) == []


def test_grype_exception_validator_rejects_expired_entries() -> None:
    errors = validate(today=date(2026, 8, 13))
    assert any("expired" in error for error in errors)
