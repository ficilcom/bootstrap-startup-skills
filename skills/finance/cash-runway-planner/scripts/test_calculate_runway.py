#!/usr/bin/env python3
"""Tests for the deterministic cash runway calculator."""

from __future__ import annotations

import calendar
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from calculate_runway import calculate, main


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def money(amount: int | float | None, evidence: str = "estimated") -> dict[str, object]:
    return {"amount": amount, "evidence": evidence}


def forecast_periods(as_of: date = date(2026, 1, 5)) -> list[dict[str, object]]:
    periods: list[dict[str, object]] = []
    start = as_of
    for index in range(13):
        end = start + timedelta(days=6)
        periods.append(
            {
                "id": f"w{index + 1:02d}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "granularity": "week",
                "movements": [],
            }
        )
        start = end + timedelta(days=1)

    horizon_end = add_months(as_of, 12) - timedelta(days=1)
    month_index = 4
    while start <= horizon_end:
        calendar_end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        end = min(calendar_end, horizon_end)
        periods.append(
            {
                "id": f"m{month_index:02d}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "granularity": "month",
                "movements": [],
            }
        )
        start = end + timedelta(days=1)
        month_index += 1
    return periods


def detailed_payload() -> dict[str, object]:
    return {
        "mode": "detailed",
        "as_of_date": "2026-01-05",
        "currency": "JPY",
        "gross_cash": money(2_000_000, "confirmed"),
        "restricted_cash": money(500_000, "confirmed"),
        "minimum_cash_buffer": money(500_000, "reported"),
        "scenarios": [{"name": "base", "periods": forecast_periods()}],
        "modeled_actions": [],
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_encoded_as_zero(self) -> None:
        payload = detailed_payload()
        payload["gross_cash"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(payload)

    def test_rejects_restricted_cash_above_gross_cash(self) -> None:
        payload = detailed_payload()
        payload["restricted_cash"] = money(2_000_001, "confirmed")
        with self.assertRaisesRegex(ValueError, "restricted_cash cannot exceed gross_cash"):
            calculate(payload)

    def test_rejects_duplicate_movement_ids(self) -> None:
        payload = detailed_payload()
        duplicate = {
            "id": "invoice-a",
            "label": "Invoice A",
            "direction": "inflow",
            "amount": money(100_000, "reported"),
        }
        periods = payload["scenarios"][0]["periods"]
        periods[0]["movements"] = [copy.deepcopy(duplicate)]
        periods[1]["movements"] = [copy.deepcopy(duplicate)]
        with self.assertRaisesRegex(ValueError, "duplicate movement id"):
            calculate(payload)

    def test_rejects_mixed_currency(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            {
                "id": "usd-invoice",
                "label": "USD invoice",
                "direction": "inflow",
                "currency": "USD",
                "amount": money(100_000, "reported"),
            }
        ]
        with self.assertRaisesRegex(ValueError, "currency must match"):
            calculate(payload)

    def test_rejects_period_gap(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][1]["start_date"] = "2026-01-13"
        with self.assertRaisesRegex(ValueError, "periods must be consecutive"):
            calculate(payload)

    def test_rejects_incomplete_detailed_weeks(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][12]["granularity"] = "month"
        with self.assertRaisesRegex(ValueError, "first 13 periods must be weekly"):
            calculate(payload)

    def test_rejects_duplicate_scenario_names(self) -> None:
        payload = detailed_payload()
        payload["scenarios"].append(copy.deepcopy(payload["scenarios"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate scenario name"):
            calculate(payload)

    def test_rejects_invalid_top_level_currency(self) -> None:
        payload = detailed_payload()
        payload["currency"] = "yen"
        with self.assertRaisesRegex(ValueError, "currency must be a three-letter code"):
            calculate(payload)


if __name__ == "__main__":
    unittest.main()
