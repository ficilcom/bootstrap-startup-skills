#!/usr/bin/env python3
"""Tests for the deterministic unit economics calculator."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

from calculate_unit_economics import calculate, main


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


if __name__ == "__main__":
    unittest.main()
