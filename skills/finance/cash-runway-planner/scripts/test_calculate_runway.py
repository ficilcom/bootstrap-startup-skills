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


def quick_periods(as_of: date = date(2026, 1, 5)) -> list[dict[str, object]]:
    periods: list[dict[str, object]] = []
    start = as_of
    horizon_end = add_months(as_of, 12) - timedelta(days=1)
    index = 1
    while start <= horizon_end:
        calendar_end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        end = min(calendar_end, horizon_end)
        periods.append(
            {
                "id": f"m{index:02d}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "granularity": "month",
                "movements": [],
            }
        )
        start = end + timedelta(days=1)
        index += 1
    return periods


def movement(
    movement_id: str,
    direction: str,
    amount: int | float | None,
    evidence: str = "estimated",
) -> dict[str, object]:
    return {
        "id": movement_id,
        "label": movement_id.replace("-", " ").title(),
        "direction": direction,
        "amount": money(amount, evidence),
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


class CalculationTests(unittest.TestCase):
    def test_stable_detailed_forecast(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            movement("weekly-tools", "outflow", 100_000, "confirmed")
        ]

        result = calculate(payload)

        base = result["scenarios"][0]
        self.assertEqual(result["opening_available_cash"], 1_500_000)
        self.assertEqual(base["periods"][0]["closing_available_cash"], 1_400_000)
        self.assertEqual(base["lowest_closing_available_cash"], 1_400_000)
        self.assertEqual(base["maximum_funding_gap"], 0)
        self.assertEqual(base["buffer_runway"], "more_than_12_months")
        self.assertEqual(base["zero_cash_runway"], "more_than_12_months")
        self.assertEqual(base["warning_status"], "stable")
        self.assertFalse(result["provisional"])

    def test_buffer_crosses_inside_thirteen_weeks_without_zero_crossing(self) -> None:
        payload = detailed_payload()
        for index in range(11):
            payload["scenarios"][0]["periods"][index]["movements"] = [
                movement(f"weekly-cost-{index}", "outflow", 100_000)
            ]

        result = calculate(payload)
        base = result["scenarios"][0]

        self.assertEqual(base["buffer_crossing_period"], "w11")
        self.assertIsNone(base["zero_crossing_period"])
        self.assertEqual(base["warning_status"], "critical")
        self.assertEqual(base["maximum_funding_gap"], 100_000)

    def test_zero_crossing_and_maximum_funding_gap(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            movement("large-payment", "outflow", 2_000_000, "confirmed")
        ]

        base = calculate(payload)["scenarios"][0]

        self.assertEqual(base["buffer_crossing_period"], "w01")
        self.assertEqual(base["zero_crossing_period"], "w01")
        self.assertEqual(base["lowest_closing_available_cash"], -500_000)
        self.assertEqual(base["maximum_funding_gap"], 1_000_000)

    def test_downside_collection_delay_changes_status(self) -> None:
        payload = detailed_payload()
        base = payload["scenarios"][0]
        base["periods"][0]["movements"] = [movement("invoice", "inflow", 1_000_000)]
        base["periods"][1]["movements"] = [movement("renewal", "outflow", 1_200_000)]
        downside = copy.deepcopy(base)
        downside["name"] = "downside"
        downside["periods"][0]["movements"] = []
        downside["periods"][9]["movements"] = [movement("invoice-delayed", "inflow", 1_000_000)]
        payload["scenarios"].append(downside)

        result = calculate(payload)
        base_result, downside_result = result["scenarios"]

        self.assertEqual(base_result["warning_status"], "stable")
        self.assertEqual(downside_result["warning_status"], "critical")
        self.assertEqual(downside_result["comparison_to_base"]["lowest_cash_delta"], -1_000_000)

    def test_payment_on_period_boundary_is_included_in_that_period(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            movement("period-end-payment", "outflow", 250_000, "reported")
        ]

        first_period = calculate(payload)["scenarios"][0]["periods"][0]

        self.assertEqual(first_period["cash_outflows"], 250_000)
        self.assertEqual(first_period["closing_available_cash"], 1_250_000)

    def test_quick_mode_is_provisional(self) -> None:
        payload = detailed_payload()
        payload["mode"] = "quick"
        payload["scenarios"][0]["periods"] = quick_periods()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            movement("normal-monthly-outflow", "outflow", 300_000)
        ]

        result = calculate(payload)

        self.assertTrue(result["provisional"])
        self.assertEqual(result["scenarios"][0]["periods"][0]["cash_outflows"], 300_000)

    def test_unknown_movement_makes_scenario_indeterminate(self) -> None:
        payload = detailed_payload()
        payload["scenarios"][0]["periods"][0]["movements"] = [
            movement("unknown-tax", "outflow", None, "unknown")
        ]

        result = calculate(payload)

        self.assertTrue(result["provisional"])
        self.assertEqual(result["warning_status"], "indeterminate")
        self.assertEqual(result["scenarios"][0]["missing_inputs"], ["movement:unknown-tax"])


class ActionAndCliTests(unittest.TestCase):
    def test_action_applies_cash_effects_and_implementation_cost(self) -> None:
        payload = detailed_payload()
        payload["modeled_actions"] = [
            {
                "id": "reduce-tools",
                "label": "Reduce unused software",
                "scenarios": ["base"],
                "start_period": "w03",
                "end_period": "w04",
                "recurrence": "expanded",
                "cash_effects": [
                    {"period_id": "w03", "amount": money(25_000)},
                    {"period_id": "w04", "amount": money(25_000)},
                ],
                "implementation_costs": [
                    {"period_id": "w03", "amount": money(10_000, "reported")}
                ],
            }
        ]

        action = calculate(payload)["modeled_actions"][0]

        self.assertEqual(action["gross_cash_effect"], 50_000)
        self.assertEqual(action["implementation_cost"], 10_000)
        self.assertEqual(action["net_cash_effect"], 40_000)
        self.assertEqual(action["adjusted"]["periods"][2]["closing_available_cash"], 1_515_000)
        self.assertEqual(action["adjusted"]["periods"][3]["closing_available_cash"], 1_540_000)
        self.assertEqual(action["delta"]["lowest_cash_delta"], 0)

    def test_action_is_recalculated_independently(self) -> None:
        payload = detailed_payload()
        payload["modeled_actions"] = [
            {
                "id": action_id,
                "label": action_id,
                "scenarios": ["base"],
                "start_period": "w01",
                "end_period": "w01",
                "recurrence": "one_time",
                "cash_effects": [{"period_id": "w01", "amount": money(amount)}],
                "implementation_costs": [],
            }
            for action_id, amount in (("action-a", 10_000), ("action-b", 20_000))
        ]

        first, second = calculate(payload)["modeled_actions"]

        self.assertEqual(first["adjusted"]["periods"][0]["closing_available_cash"], 1_510_000)
        self.assertEqual(second["adjusted"]["periods"][0]["closing_available_cash"], 1_520_000)

    def test_rejects_duplicate_action_ids(self) -> None:
        payload = detailed_payload()
        action = {
            "id": "same-action",
            "label": "Same action",
            "scenarios": ["base"],
            "start_period": "w01",
            "end_period": "w01",
            "recurrence": "one_time",
            "cash_effects": [{"period_id": "w01", "amount": money(10_000)}],
            "implementation_costs": [],
        }
        payload["modeled_actions"] = [copy.deepcopy(action), copy.deepcopy(action)]

        with self.assertRaisesRegex(ValueError, "duplicate action id"):
            calculate(payload)

    def test_rejects_action_without_effective_period(self) -> None:
        payload = detailed_payload()
        payload["modeled_actions"] = [
            {
                "id": "missing-period",
                "label": "Missing period",
                "scenarios": ["base"],
                "start_period": "w01",
                "end_period": "w01",
                "recurrence": "one_time",
                "cash_effects": [{"amount": money(10_000)}],
                "implementation_costs": [],
            }
        ]

        with self.assertRaisesRegex(ValueError, "period_id"):
            calculate(payload)

    def test_cli_outputs_json_for_valid_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text(json.dumps(detailed_payload()), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main([str(path)])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["warning_status"], "stable")

    def test_cli_reports_malformed_json_to_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.json"
            path.write_text("{broken", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main([str(path)])

        self.assertEqual(status, 2)
        self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
