#!/usr/bin/env python3
"""Tests for the deterministic first-hire affordability calculator."""

from __future__ import annotations

import copy
import io
import json
import runpy
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/hiring/first-hire-affordability/scripts/calculate_affordability.py"
MODULE = runpy.run_path(str(SCRIPT))
calculate = MODULE["calculate"]
main = MODULE["main"]


def money(amount: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "evidence": evidence}


def rate(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def costs() -> dict[str, object]:
    return {
        "annual_salary": money(1_200),
        "employer_contributions_rate": rate(0.10, "estimated"),
        "benefits_monthly": money(10, "estimated"),
        "recruiting_one_time": money(100),
        "equipment_software_one_time": money(50, "estimated"),
        "equipment_software_monthly": money(10),
        "onboarding_one_time": money(50, "estimated"),
        "management_time_monthly": money(10, "estimated"),
        "separation_contingency_one_time": money(0, "reported"),
        "productivity_ramp_costs": [money(100, "estimated"), money(0, "estimated")],
        "benefit_ramp_monthly": [money(0, "estimated"), money(100, "estimated"), money(200, "estimated")],
    }


def scenario(name: str, start: int, *, inflows: int = 2_000, outflows: int = 1_000) -> dict[str, object]:
    return {
        "name": name,
        "hire_start_month": start,
        "pre_hire_monthly_cash": {"inflows": money(inflows), "outflows": money(outflows)},
        "pre_hire_adjustments": [],
        "hiring_costs": costs(),
    }


def payload(*, opening: int = 10_000, buffer: int = 2_000, horizon: int = 12) -> dict[str, object]:
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "opening_available_cash": money(opening),
        "minimum_cash_buffer": money(buffer, "reported"),
        "planning_horizon_months": horizon,
        "scenarios": [scenario("base", 0), scenario("downside", 0), scenario("delayed", 2)],
    }


class ValidationTests(unittest.TestCase):
    def test_requires_all_three_named_scenarios(self) -> None:
        data = payload()
        data["scenarios"].pop()
        with self.assertRaisesRegex(ValueError, "exactly base, downside, and delayed"):
            calculate(data)

    def test_rejects_delayed_scenario_starting_now(self) -> None:
        data = payload()
        data["scenarios"][2]["hire_start_month"] = 0
        with self.assertRaisesRegex(ValueError, "delayed.hire_start_month"):
            calculate(data)

    def test_rejects_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["scenarios"][0]["hiring_costs"]["annual_salary"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(data)

    def test_rejects_rate_above_one(self) -> None:
        data = payload()
        data["scenarios"][0]["hiring_costs"]["employer_contributions_rate"] = rate(1.01)
        with self.assertRaisesRegex(ValueError, "from 0 through 1"):
            calculate(data)

    def test_rejects_duplicate_adjustment_months(self) -> None:
        data = payload()
        adjustment = {"month_index": 1, "inflows": money(0), "outflows": money(10)}
        data["scenarios"][0]["pre_hire_adjustments"] = [adjustment, copy.deepcopy(adjustment)]
        with self.assertRaisesRegex(ValueError, "must not repeat month_index"):
            calculate(data)


class CalculationTests(unittest.TestCase):
    def test_calculates_fully_loaded_costs_cash_and_payback(self) -> None:
        result = calculate(payload())
        base = result["scenarios"][0]

        self.assertEqual(base["status"], "maintains_buffer")
        self.assertEqual(base["periods"][0]["pre_hire_closing_cash"], 11_000)
        self.assertEqual(base["periods"][0]["hire_cost"], 440)
        self.assertEqual(base["periods"][0]["closing_cash"], 10_560)
        self.assertEqual(base["cost_component_totals"]["salary_monthly"], 1_200)
        self.assertEqual(base["cost_component_totals"]["employer_contributions_monthly"], 120)
        self.assertEqual(base["total_hire_cost"], 1_980)
        self.assertEqual(base["total_hire_benefit_cash"], 2_100)
        self.assertEqual(base["benefit_payback_month"], 9)
        self.assertEqual(result["recommendation"]["outcome"], "hire_now")
        self.assertTrue(result["provisional"])

    def test_returns_conditional_when_downside_breaks_buffer(self) -> None:
        data = payload()
        data["scenarios"][1]["pre_hire_monthly_cash"] = {"inflows": money(0), "outflows": money(1_000)}
        result = calculate(data)

        self.assertEqual(result["recommendation"]["outcome"], "conditional")
        self.assertEqual(result["scenarios"][1]["status"], "cash_shortfall")
        self.assertGreater(result["scenarios"][1]["maximum_buffer_funding_gap"], 0)
        self.assertEqual(result["recommendation"]["earliest_affordable_hire_start_month"], None)

    def test_finds_later_robust_start_and_recommends_deferral(self) -> None:
        data = payload(opening=2_000, buffer=2_000)
        for item in data["scenarios"]:
            item["pre_hire_monthly_cash"] = {"inflows": money(1_100), "outflows": money(1_000)}
        result = calculate(data)

        self.assertEqual(result["recommendation"]["outcome"], "defer")
        self.assertEqual(result["recommendation"]["earliest_affordable_hire_start_month"], 4)

    def test_unknown_important_input_is_indeterminate(self) -> None:
        data = payload()
        data["scenarios"][1]["hiring_costs"]["benefits_monthly"] = money(None, "unknown")
        result = calculate(data)

        self.assertEqual(result["recommendation"]["outcome"], "indeterminate")
        self.assertEqual(result["scenarios"][1]["status"], "indeterminate")
        self.assertIn("scenarios.downside.hiring_costs.benefits_monthly", result["scenarios"][1]["missing_inputs"])

    def test_adjustments_affect_their_month_without_changing_regular_cash(self) -> None:
        data = payload()
        data["scenarios"][0]["pre_hire_adjustments"] = [
            {"month_index": 1, "inflows": money(0), "outflows": money(500)}
        ]
        result = calculate(data)["scenarios"][0]

        self.assertEqual(result["periods"][1]["pre_hire_outflows"], 1_500)
        self.assertEqual(result["periods"][2]["pre_hire_outflows"], 1_000)


class CommandLineTests(unittest.TestCase):
    def test_main_prints_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as input_file:
            json.dump(payload(), input_file)
            input_file.flush()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main([input_file.name]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["recommendation"]["outcome"], "hire_now")

    def test_main_uses_exit_code_two_for_invalid_input(self) -> None:
        stderr = io.StringIO()
        with patch("sys.stdin", io.StringIO("{}")), redirect_stderr(stderr):
            self.assertEqual(main(["-"]), 2)
        self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
