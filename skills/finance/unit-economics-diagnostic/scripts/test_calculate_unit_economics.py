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

    def test_rejects_ltv_period_mismatch(self) -> None:
        payload = recurring_payload()
        payload["scenarios"][0]["ltv_model"]["period_unit"] = "quarter"
        with self.assertRaisesRegex(ValueError, "period_unit must match analysis_period"):
            calculate(payload)


if __name__ == "__main__":
    unittest.main()
