#!/usr/bin/env python3
"""Tests for the deterministic work-coverage comparison calculator."""

from __future__ import annotations

import copy
import io
import json
import runpy
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/hiring/hire-outsource-automate/scripts/compare_options.py"
MODULE = runpy.run_path(str(SCRIPT))
calculate = MODULE["calculate"]
main = MODULE["main"]
COST_FIELDS = MODULE["COST_FIELDS"]


def money(amount: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def candidate(kind: str = "hire", name: str = "hire") -> dict[str, object]:
    costs = {
        bucket: {field: money(0) for field in fields}
        for bucket, fields in COST_FIELDS[kind].items()
    }
    if kind == "hire":
        costs["one_time"].update(
            {
                "recruiting": money(100),
                "onboarding": money(20),
                "equipment": money(10),
            }
        )
        costs["recurring_per_period"].update(
            {
                "compensation": money(50),
                "employer_burdens_and_benefits": money(10),
                "management": money(10),
                "tools_and_workspace": money(5),
            }
        )
    return {
        "name": name,
        "kind": kind,
        "fit": {
            "workload_hours_per_period": scalar(120, "reported"),
            "workload_variability": "volatile",
            "strategic_importance": "high",
            "confidentiality": "medium",
            "quality_control": "direct",
            "time_to_readiness_periods": scalar(2, "estimated"),
            "reversibility": "low",
            "internal_learning_value": "high",
            "management_overhead_hours_per_period": scalar(8, "estimated"),
        },
        "costs": costs,
        "benefits_per_ready_period": [
            {"category": "cost_avoidance", "label": "Founder time", "amount": money(200, "estimated")},
            {"category": "loss_avoidance", "label": "Rework avoided", "amount": money(50, "reported")},
        ],
        "pessimistic_case": {
            "benefit_multiplier": scalar(0.5, "estimated"),
            "cost_multiplier": scalar(1.1, "estimated"),
        },
    }


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "period_unit": "month",
        "horizon_periods": 4,
        "candidates": [candidate()],
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_money_encoded_as_zero(self) -> None:
        value = payload()
        value["candidates"][0]["costs"]["one_time"]["recruiting"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(value)

    def test_rejects_unknown_scalar_encoded_as_zero(self) -> None:
        value = payload()
        value["candidates"][0]["fit"]["time_to_readiness_periods"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown value must be null"):
            calculate(value)

    def test_rejects_nonstandard_cost_bucket_fields(self) -> None:
        value = payload()
        del value["candidates"][0]["costs"]["recurring_per_period"]["management"]
        with self.assertRaisesRegex(ValueError, "exactly the required cost fields"):
            calculate(value)

    def test_rejects_currency_mismatch(self) -> None:
        value = payload()
        value["candidates"][0]["costs"]["one_time"]["recruiting"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "must match top-level currency"):
            calculate(value)

    def test_rejects_pessimistic_benefit_multiplier_above_one(self) -> None:
        value = payload()
        value["candidates"][0]["pessimistic_case"]["benefit_multiplier"] = scalar(1.01)
        with self.assertRaisesRegex(ValueError, "must be at most 1"):
            calculate(value)

    def test_rejects_duplicate_candidate_names(self) -> None:
        value = payload()
        value["candidates"].append(copy.deepcopy(value["candidates"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate candidate name"):
            calculate(value)


class CalculationTests(unittest.TestCase):
    def test_calculates_comparable_cost_benefit_payback_and_downside(self) -> None:
        result = calculate(payload())["candidates"][0]

        self.assertEqual(result["fit"]["workload_hours_per_period"], {"value": 120, "evidence": "reported"})
        self.assertEqual(result["benefit_by_category_per_ready_period"]["cost_avoidance"], 200)
        self.assertEqual(result["benefit_by_category_per_ready_period"]["loss_avoidance"], 50)
        self.assertEqual(result["base_case"]["one_time_cost"], 130)
        self.assertEqual(result["base_case"]["recurring_cost_per_period"], 75)
        self.assertEqual(result["base_case"]["total_cost"], 430)
        self.assertEqual(result["base_case"]["total_quantified_benefit"], 500)
        self.assertEqual(result["base_case"]["net_quantified_effect"], 70)
        self.assertEqual(result["base_case"]["payback_periods"], 4)
        self.assertEqual(result["pessimistic_case"]["total_cost"], 473)
        self.assertEqual(result["pessimistic_case"]["total_quantified_benefit"], 250)
        self.assertEqual(result["pessimistic_case"]["net_quantified_effect"], -223)
        self.assertTrue(result["estimate_based"])

    def test_unknown_core_economic_input_returns_no_partial_numeric_conclusion(self) -> None:
        value = payload()
        value["candidates"][0]["costs"]["recurring_per_period"]["compensation"] = money(None, "unknown")

        result = calculate(value)["candidates"][0]

        self.assertEqual(result["base_case"], "indeterminate")
        self.assertEqual(result["pessimistic_case"], "not_calculated_due_to_unknown_base_inputs")
        self.assertIn("costs.recurring_per_period.compensation", result["missing_inputs"])
        self.assertEqual(calculate(value)["economic_ranking"], [])

    def test_unknown_non_economic_fit_input_remains_separate_from_cost_math(self) -> None:
        value = payload()
        value["candidates"][0]["fit"]["workload_hours_per_period"] = scalar(None, "unknown")

        result = calculate(value)["candidates"][0]

        self.assertIsInstance(result["base_case"], dict)
        self.assertIn("fit.workload_hours_per_period", result["missing_inputs"])

    def test_ranking_is_economic_only_and_excludes_indeterminate_options(self) -> None:
        value = payload()
        outsource = candidate("outsource", "outsource")
        outsource["fit"]["time_to_readiness_periods"] = scalar(0)
        outsource["costs"]["recurring_per_period"]["contract"] = money(20)
        outsource["benefits_per_ready_period"] = [
            {"category": "incremental_revenue", "label": "Delivery", "amount": money(100)}
        ]
        outsource.pop("pessimistic_case")
        value["candidates"].append(outsource)

        result = calculate(value)

        self.assertEqual(result["economic_ranking"], ["outsource", "hire"])
        self.assertIn("qualitative fit", result["economic_ranking_scope"])

    def test_all_supported_option_kinds_are_calculable(self) -> None:
        value = payload()
        value["candidates"] = [candidate(kind, kind) for kind in COST_FIELDS]
        for item in value["candidates"]:
            item.pop("pessimistic_case")

        result = calculate(value)

        self.assertEqual(len(result["economic_ranking"]), 4)
        self.assertTrue(all(isinstance(item["base_case"], dict) for item in result["candidates"]))


class CommandLineTests(unittest.TestCase):
    def test_main_writes_json_for_valid_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as stream:
            json.dump(payload(), stream)
            stream.flush()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main([stream.name])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["currency"], "JPY")

    def test_main_reports_validation_error(self) -> None:
        stderr = io.StringIO()
        with patch("sys.stdin", io.StringIO("{}")), redirect_stderr(stderr):
            status = main(["-"])

        self.assertEqual(status, 2)
        self.assertIn("error: input must contain", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
