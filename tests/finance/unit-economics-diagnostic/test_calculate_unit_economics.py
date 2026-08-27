#!/usr/bin/env python3
"""Tests for the deterministic unit economics calculator."""

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
SCRIPT = ROOT / "skills/finance/unit-economics-diagnostic/scripts/calculate_unit_economics.py"
UNIT_ECONOMICS_MODULE = runpy.run_path(str(SCRIPT))
calculate = UNIT_ECONOMICS_MODULE["calculate"]
main = UNIT_ECONOMICS_MODULE["main"]


def money(
    amount: int | float | None,
    evidence: str = "confirmed",
    currency: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {"amount": amount, "evidence": evidence}
    if currency is not None:
        result["currency"] = currency
    return result


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def recurring_payload() -> dict[str, object]:
    return {
        "mode": "recurring",
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "analysis_period": "month",
        "unit_name": "active-customer-month",
        "unit_is_discrete": True,
        "revenue_basis": "net subscription revenue",
        "scenarios": [
            {
                "name": "base",
                "drivers": {
                    "price_per_unit": money(12_000),
                    "cogs_per_unit": money(2_500, "reported"),
                    "other_variable_cost_per_unit": money(1_000, "estimated"),
                    "volume_units": scalar(180, "reported"),
                    "fixed_costs": money(1_200_000),
                    "new_customers": scalar(30),
                    "units_per_customer_per_period": scalar(1, "reported"),
                    "capacity_units": scalar(220, "estimated"),
                },
                "acquisition": {
                    "decision_cac_basis": "fully_loaded",
                    "decision_cac_scope_complete": True,
                    "selected_pool_matches_customer_cohort": True,
                    "selected_pool_included_in_fixed_costs": True,
                    "marginal_new_customers": scalar(10, "estimated"),
                    "costs": {
                        "paid": money(240_000),
                        "blended": money(420_000, "reported"),
                        "fully_loaded": money(600_000, "estimated"),
                        "marginal": money(180_000, "estimated"),
                    },
                },
                "ltv_model": {
                    "method": "constant_retention",
                    "churn_rate_per_period": scalar(0.04, "estimated"),
                    "period_unit": "month",
                },
                "targets": {
                    "max_payback_periods": scalar(8, "reported"),
                },
            }
        ],
        "sensitivity_cases": [],
    }


def use_fixed_horizon(payload: dict[str, object], *, expected_units: float = 5, horizon: int = 12) -> None:
    payload["scenarios"][0]["ltv_model"] = {
        "method": "fixed_horizon",
        "expected_units_per_customer_within_horizon": scalar(expected_units, "estimated"),
        "horizon_periods": scalar(horizon, "reported"),
        "period_unit": payload["analysis_period"],
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_money_encoded_as_zero(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["price_per_unit"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(payload)

    def test_rejects_unknown_scalar_encoded_as_zero(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["volume_units"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown value must be null"):
            calculate(payload)

    def test_rejects_constant_retention_for_transactional_mode(self) -> None:
        payload = recurring_payload()
        payload["mode"] = "transactional"
        with self.assertRaisesRegex(ValueError, "constant_retention is only valid for recurring"):
            calculate(payload)

    def test_rejects_invalid_currency(self) -> None:
        payload = recurring_payload()
        payload["currency"] = "yen"
        with self.assertRaisesRegex(ValueError, "currency must be a three-letter code"):
            calculate(payload)

    def test_rejects_mixed_money_currency(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["price_per_unit"] = money(12_000, currency="USD")
        with self.assertRaisesRegex(ValueError, "currency must match"):
            calculate(payload)

    def test_rejects_rate_above_one(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"]["churn_rate_per_period"] = scalar(1.01)
        with self.assertRaisesRegex(ValueError, "must be from 0 through 1"):
            calculate(payload)

    def test_rejects_negative_scalar(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["volume_units"] = scalar(-1)
        with self.assertRaisesRegex(ValueError, "must be nonnegative"):
            calculate(payload)

    def test_rejects_duplicate_scenario_names(self) -> None:
        payload = recurring_payload()
        payload["scenarios"].append(copy.deepcopy(payload["scenarios"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate scenario name"):
            calculate(payload)

    def test_rejects_missing_selected_cac_basis(self) -> None:
        payload = recurring_payload()
        del payload["scenarios"][0]["acquisition"]["costs"]["fully_loaded"]
        with self.assertRaisesRegex(ValueError, "decision_cac_basis must be present"):
            calculate(payload)

    def test_rejects_marginal_cost_without_incremental_customers(self) -> None:
        payload = recurring_payload()
        del payload["scenarios"][0]["acquisition"]["marginal_new_customers"]
        with self.assertRaisesRegex(ValueError, "marginal_new_customers is required"):
            calculate(payload)

    def test_rejects_nonboolean_scope_flag(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["acquisition"]["decision_cac_scope_complete"] = "yes"
        with self.assertRaisesRegex(ValueError, "decision_cac_scope_complete must be a boolean"):
            calculate(payload)

    def test_rejects_fractional_customer_count(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["new_customers"] = scalar(2.5)
        with self.assertRaisesRegex(ValueError, "new_customers must be a whole number"):
            calculate(payload)

    def test_rejects_fractional_volume_for_discrete_unit(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["volume_units"] = scalar(180.5)
        with self.assertRaisesRegex(ValueError, "volume_units must be a whole number"):
            calculate(payload)

    def test_rejects_fractional_capacity_for_discrete_unit(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["capacity_units"] = scalar(220.5)
        with self.assertRaisesRegex(ValueError, "capacity_units must be a whole number"):
            calculate(payload)

    def test_rejects_ltv_period_mismatch(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"]["period_unit"] = "quarter"
        with self.assertRaisesRegex(ValueError, "period_unit must match analysis_period"):
            calculate(payload)


class UnitProfitTests(unittest.TestCase):
    def test_calculates_unit_profit_period_totals_and_break_even(self) -> None:
        result = calculate(recurring_payload())["scenarios"][0]

        self.assertEqual(result["unit_economics"]["gross_profit_per_unit"], 9_500)
        self.assertEqual(result["unit_economics"]["gross_margin"], Decimal("0.7916666666666666666666666667"))
        self.assertEqual(result["unit_economics"]["contribution_profit_per_unit"], 8_500)
        self.assertEqual(result["unit_economics"]["contribution_margin"], Decimal("0.7083333333333333333333333333"))
        self.assertEqual(result["period_economics"]["revenue"], 2_160_000)
        self.assertEqual(result["period_economics"]["contribution_after_fixed_costs"], 330_000)
        self.assertEqual(result["break_even"]["units_ceiling"], 142)
        self.assertEqual(result["break_even"]["capacity_status"], "within_capacity")

    def test_zero_price_keeps_absolute_values_and_types_percentages(self) -> None:
        payload = recurring_payload()
        drivers = payload["scenarios"][0]["drivers"]
        drivers["price_per_unit"] = money(0)
        drivers["cogs_per_unit"] = money(0)
        drivers["other_variable_cost_per_unit"] = money(0)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["unit_economics"]["gross_profit_per_unit"], 0)
        self.assertEqual(result["unit_economics"]["gross_margin"], "indeterminate_zero_price")
        self.assertEqual(result["unit_economics"]["contribution_margin"], "indeterminate_zero_price")
        self.assertEqual(result["break_even"]["units"], "no_finite_break_even")

    def test_negative_transactional_contribution_has_no_finite_break_even(self) -> None:
        payload = recurring_payload()
        payload["mode"] = "transactional"
        use_fixed_horizon(payload)
        drivers = payload["scenarios"][0]["drivers"]
        drivers["price_per_unit"] = money(1_000)
        drivers["cogs_per_unit"] = money(700)
        drivers["other_variable_cost_per_unit"] = money(400)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["unit_economics"]["contribution_profit_per_unit"], -100)
        self.assertEqual(result["break_even"]["units"], "no_finite_break_even")
        self.assertEqual(result["break_even"]["revenue"], "no_finite_break_even")

    def test_continuous_unit_keeps_raw_break_even_without_ceiling(self) -> None:
        payload = recurring_payload()
        payload["unit_is_discrete"] = False
        drivers = payload["scenarios"][0]["drivers"]
        drivers["price_per_unit"] = money(100)
        drivers["cogs_per_unit"] = money(20)
        drivers["other_variable_cost_per_unit"] = money(10)
        drivers["fixed_costs"] = money(150)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["break_even"]["units"], Decimal("2.142857142857142857142857143"))
        self.assertEqual(result["break_even"]["units_ceiling"], "not_applicable_continuous_unit")

    def test_service_break_even_can_exceed_capacity(self) -> None:
        payload = recurring_payload()
        payload["mode"] = "service_project"
        payload["unit_name"] = "project"
        use_fixed_horizon(payload, expected_units=2, horizon=12)
        drivers = payload["scenarios"][0]["drivers"]
        drivers["price_per_unit"] = money(100_000)
        drivers["cogs_per_unit"] = money(40_000)
        drivers["other_variable_cost_per_unit"] = money(10_000)
        drivers["fixed_costs"] = money(1_000_000)
        drivers["capacity_units"] = scalar(10)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["break_even"]["units_ceiling"], 20)
        self.assertEqual(result["break_even"]["capacity_status"], "beyond_capacity")

    def test_zero_fixed_cost_has_zero_break_even(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["fixed_costs"] = money(0)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["break_even"]["units"], 0)
        self.assertEqual(result["break_even"]["units_ceiling"], 0)
        self.assertEqual(result["break_even"]["revenue"], 0)

    def test_unknown_cogs_does_not_become_zero(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["cogs_per_unit"] = money(None, "unknown")

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["unit_economics"]["gross_profit_per_unit"], "indeterminate")
        self.assertEqual(result["unit_economics"]["contribution_profit_per_unit"], "indeterminate")
        self.assertIn("drivers.cogs_per_unit", result["missing_inputs"])

    def test_returns_current_volume_price_breakpoint(self) -> None:
        result = calculate(recurring_payload())["scenarios"][0]

        self.assertEqual(result["breakpoints"]["minimum_price_for_positive_contribution"], 3_500)
        self.assertEqual(
            result["breakpoints"]["minimum_price_for_break_even_at_current_volume"],
            Decimal("10166.66666666666666666666667"),
        )
        self.assertEqual(result["breakpoints"]["maximum_variable_cost_for_positive_contribution"], 9_500)


class CustomerEconomicsTests(unittest.TestCase):
    def test_calculates_each_cac_basis_payback_and_constant_retention_ltv(self) -> None:
        result = calculate(recurring_payload())["scenarios"][0]

        self.assertEqual(result["cac"]["by_basis"]["paid"], 8_000)
        self.assertEqual(result["cac"]["by_basis"]["blended"], 14_000)
        self.assertEqual(result["cac"]["by_basis"]["fully_loaded"], 20_000)
        self.assertEqual(result["cac"]["by_basis"]["marginal"], 18_000)
        self.assertEqual(result["cac"]["selected_basis"], "fully_loaded")
        self.assertEqual(result["cac"]["selected_cac"], 20_000)
        self.assertEqual(result["customer_economics"]["contribution_per_period"], 8_500)
        self.assertEqual(
            result["customer_economics"]["payback_periods"],
            Decimal("2.352941176470588235294117647"),
        )
        self.assertEqual(result["customer_economics"]["ltv"], 212_500)
        self.assertEqual(result["customer_economics"]["expected_lifetime_periods"], 25)
        self.assertEqual(result["customer_economics"]["ltv_to_cac"], Decimal("10.625"))

    def test_zero_churn_does_not_return_infinite_ltv(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"]["churn_rate_per_period"] = scalar(0)

        result = calculate(payload)["scenarios"][0]["customer_economics"]

        self.assertEqual(result["ltv"], "zero_churn_requires_fixed_horizon_or_cohort")
        self.assertEqual(
            result["expected_lifetime_periods"],
            "zero_churn_requires_fixed_horizon_or_cohort",
        )
        self.assertEqual(result["ltv_to_cac"], "indeterminate")

    def test_fixed_horizon_transactional_ltv(self) -> None:
        payload = recurring_payload()
        payload["mode"] = "transactional"
        use_fixed_horizon(payload, expected_units=5, horizon=12)

        result = calculate(payload)["scenarios"][0]["customer_economics"]

        self.assertEqual(result["ltv_method"], "fixed_horizon")
        self.assertEqual(result["ltv"], 42_500)
        self.assertEqual(result["ltv_horizon_periods"], 12)
        self.assertEqual(result["ltv_to_cac"], Decimal("2.125"))

    def test_observed_cohort_uses_cumulative_payback_without_extrapolation(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"] = {
            "method": "observed_cohort",
            "cohort_customers": scalar(40),
            "contribution_totals_by_period": [money(320_000), money(480_000), money(240_000)],
            "period_unit": "month",
        }

        result = calculate(payload)["scenarios"][0]["customer_economics"]

        self.assertEqual(result["payback_periods"], 2)
        self.assertEqual(result["ltv"], 26_000)
        self.assertEqual(result["ltv_horizon_periods"], 3)

        payload["scenarios"][0]["ltv_model"]["contribution_totals_by_period"] = [money(100_000)]
        result = calculate(payload)["scenarios"][0]["customer_economics"]
        self.assertEqual(result["payback_periods"], "not_observed_within_horizon")

    def test_zero_customer_denominators_return_typed_states(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["new_customers"] = scalar(0)
        payload["scenarios"][0]["acquisition"]["marginal_new_customers"] = scalar(0)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["cac"]["by_basis"]["paid"], "indeterminate_zero_new_customers")
        self.assertEqual(
            result["cac"]["by_basis"]["marginal"],
            "indeterminate_zero_marginal_new_customers",
        )
        self.assertEqual(result["customer_economics"]["payback_periods"], "indeterminate")

    def test_zero_selected_cac_has_typed_ratio(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["acquisition"]["costs"]["fully_loaded"] = money(0)

        result = calculate(payload)["scenarios"][0]["customer_economics"]

        self.assertEqual(result["payback_periods"], 0)
        self.assertEqual(result["ltv_to_cac"], "not_meaningful_zero_cac")

    def test_nonpositive_customer_contribution_is_not_recoverable(self) -> None:
        payload = recurring_payload()
        payload["mode"] = "transactional"
        use_fixed_horizon(payload)
        drivers = payload["scenarios"][0]["drivers"]
        drivers["price_per_unit"] = money(1_000)
        drivers["cogs_per_unit"] = money(700)
        drivers["other_variable_cost_per_unit"] = money(400)

        result = calculate(payload)["scenarios"][0]

        self.assertEqual(result["customer_economics"]["payback_periods"], "not_recoverable")
        self.assertIn("negative_unit_economics", result["diagnostic_flags"])
        self.assertIn("acquisition_not_recovered", result["diagnostic_flags"])


class DiagnosticTests(unittest.TestCase):
    def test_complete_base_case_supports_profitable_to_scale(self) -> None:
        flags = calculate(recurring_payload())["scenarios"][0]["diagnostic_flags"]

        self.assertIn("profitable_to_scale", flags)
        self.assertNotIn("positive_unit_economics_unassessed_acquisition", flags)

    def test_incomplete_or_misaligned_cac_scope_prevents_scale_claim(self) -> None:
        for field in ("decision_cac_scope_complete", "selected_pool_matches_customer_cohort"):
            with self.subTest(field=field):
                payload = recurring_payload()
                payload["scenarios"][0]["acquisition"][field] = False

                flags = calculate(payload)["scenarios"][0]["diagnostic_flags"]

                self.assertNotIn("profitable_to_scale", flags)
                self.assertIn("positive_unit_economics_unassessed_acquisition", flags)

    def test_target_exceeded_but_ltv_recovers_cac_is_cash_hungry(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["targets"]["max_payback_periods"] = scalar(1)

        flags = calculate(payload)["scenarios"][0]["diagnostic_flags"]

        self.assertIn("unit_positive_but_cash_hungry", flags)
        self.assertNotIn("acquisition_not_recovered", flags)
        self.assertNotIn("profitable_to_scale", flags)

    def test_break_even_beyond_capacity_is_flagged(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["capacity_units"] = scalar(100)

        flags = calculate(payload)["scenarios"][0]["diagnostic_flags"]

        self.assertIn("break_even_beyond_capacity", flags)
        self.assertNotIn("profitable_to_scale", flags)

    def test_unknown_unit_input_is_indeterminate(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["drivers"]["cogs_per_unit"] = money(None, "unknown")

        flags = calculate(payload)["scenarios"][0]["diagnostic_flags"]

        self.assertIn("indeterminate", flags)

    def test_returns_acquisition_breakpoints_and_clamps_churn(self) -> None:
        result = calculate(recurring_payload())["scenarios"][0]["breakpoints"]

        self.assertEqual(result["maximum_cac_for_payback_target"], 68_000)
        self.assertEqual(result["maximum_constant_churn_for_ltv_equal_cac"], Decimal("0.425"))
        self.assertEqual(result["maximum_constant_churn_constraint"], "within_probability_range")

        payload = recurring_payload()
        payload["scenarios"][0]["acquisition"]["costs"]["fully_loaded"] = money(5_000)
        result = calculate(payload)["scenarios"][0]["breakpoints"]
        self.assertEqual(result["maximum_constant_churn_for_ltv_equal_cac"], 1)
        self.assertEqual(result["maximum_constant_churn_constraint"], "clamped_to_one")


class ScenarioAndSensitivityTests(unittest.TestCase):
    def test_scenario_comparison_reports_decision_metric_deltas(self) -> None:
        payload = recurring_payload()
        downside = copy.deepcopy(payload["scenarios"][0])
        downside["name"] = "downside"
        downside["drivers"]["price_per_unit"] = money(8_000, "estimated")
        downside["acquisition"]["costs"]["fully_loaded"] = money(900_000, "estimated")
        payload["scenarios"].append(downside)

        result = calculate(payload)["scenarios"][1]

        self.assertEqual(result["unit_economics"]["contribution_profit_per_unit"], 4_500)
        self.assertEqual(result["cac"]["selected_cac"], 30_000)
        self.assertEqual(result["comparison_to_base"]["deltas"]["contribution_profit_per_unit"], -4_000)
        self.assertEqual(result["comparison_to_base"]["deltas"]["selected_cac"], 10_000)
        self.assertIn("profitable_to_scale", result["comparison_to_base"]["removed_flags"])

    def test_sensitivity_cases_recalculate_independently(self) -> None:
        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "price-down-and-cogs-up",
                "source_scenario": "base",
                "overrides": {
                    "drivers.price_per_unit": money(10_800, "estimated"),
                    "drivers.cogs_per_unit": money(3_000, "estimated"),
                },
            },
            {
                "name": "cogs-only",
                "source_scenario": "base",
                "overrides": {
                    "drivers.cogs_per_unit": money(3_000, "estimated"),
                },
            },
        ]

        cases = calculate(payload)["sensitivity_cases"]

        self.assertEqual(cases[0]["source_scenario"], "base")
        self.assertEqual(cases[0]["unit_economics"]["contribution_profit_per_unit"], 6_800)
        self.assertIn("contribution_profit_per_unit", cases[0]["deltas"])
        self.assertEqual(cases[1]["unit_economics"]["contribution_profit_per_unit"], 8_000)

    def test_sensitivity_reports_added_and_removed_flags(self) -> None:
        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "capacity-crunch",
                "source_scenario": "base",
                "overrides": {"drivers.capacity_units": scalar(100, "estimated")},
            }
        ]

        case = calculate(payload)["sensitivity_cases"][0]

        self.assertIn("break_even_beyond_capacity", case["added_flags"])
        self.assertIn("profitable_to_scale", case["removed_flags"])

    def test_observed_cohort_list_can_be_overridden(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"] = {
            "method": "observed_cohort",
            "cohort_customers": scalar(40),
            "contribution_totals_by_period": [money(320_000), money(480_000)],
            "period_unit": "month",
        }
        payload["sensitivity_cases"] = [
            {
                "name": "cohort-downside",
                "source_scenario": "base",
                "overrides": {
                    "ltv_model.contribution_totals_by_period": [money(200_000), money(200_000)]
                },
            }
        ]

        case = calculate(payload)["sensitivity_cases"][0]

        self.assertEqual(case["customer_economics"]["ltv"], 10_000)
        self.assertEqual(case["customer_economics"]["payback_periods"], "not_observed_within_horizon")
        self.assertIn("acquisition_not_recovered", case["added_flags"])

    def test_rejects_structural_sensitivity_override(self) -> None:
        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "invalid",
                "source_scenario": "base",
                "overrides": {"ltv_model.method": "fixed_horizon"},
            }
        ]

        with self.assertRaisesRegex(ValueError, "unsupported sensitivity override path"):
            calculate(payload)

    def test_rejects_duplicate_sensitivity_names_and_unknown_sources(self) -> None:
        payload = recurring_payload()
        case = {
            "name": "duplicate",
            "source_scenario": "base",
            "overrides": {"drivers.price_per_unit": money(10_000, "estimated")},
        }
        payload["sensitivity_cases"] = [case, copy.deepcopy(case)]
        with self.assertRaisesRegex(ValueError, "duplicate sensitivity name"):
            calculate(payload)

        payload["sensitivity_cases"] = [copy.deepcopy(case)]
        payload["sensitivity_cases"][0]["source_scenario"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown source scenario"):
            calculate(payload)


class CliTests(unittest.TestCase):
    def test_reads_valid_file_and_prints_compact_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            input_path.write_text(json.dumps(recurring_payload()), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = main([str(input_path)])

        self.assertEqual(status, 0)
        self.assertNotIn("\n ", stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["scenarios"][0]["cac"]["selected_cac"], 20_000)

    def test_reads_standard_input(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(recurring_payload()))), redirect_stdout(stdout):
            status = main(["-"])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["mode"], "recurring")

    def test_malformed_json_and_validation_errors_return_two(self) -> None:
        for raw in ("{", json.dumps({"mode": "hybrid"})):
            with self.subTest(raw=raw):
                stderr = io.StringIO()
                with patch("sys.stdin", io.StringIO(raw)), redirect_stderr(stderr):
                    status = main(["-"])
                self.assertEqual(status, 2)
                self.assertTrue(stderr.getvalue().startswith("error: "))


if __name__ == "__main__":
    unittest.main()
