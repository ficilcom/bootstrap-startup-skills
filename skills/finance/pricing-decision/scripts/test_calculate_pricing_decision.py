#!/usr/bin/env python3
"""Tests for the deterministic pricing decision calculator."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from calculate_pricing_decision import calculate, calculate_charge, main


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


def flat_plan(name: str, fee: int) -> dict[str, object]:
    return {
        "name": name,
        "package_label": name.replace("-", " ").title(),
        "pricing": {"model": "flat", "flat_fee": money(fee)},
    }


def usage_plan(
    *,
    name: str = "usage-plan",
    base: int = 10_000,
    included: int = 5,
    excess: int = 2_000,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, object]:
    pricing: dict[str, object] = {
        "model": "base_plus_usage",
        "base_fee": money(base),
        "included_usage_units": scalar(included),
        "price_per_excess_unit": money(excess),
    }
    if minimum is not None:
        pricing["minimum_fee"] = money(minimum)
    if maximum is not None:
        pricing["maximum_fee"] = money(maximum)
    return {"name": name, "package_label": "Usage", "pricing": pricing}


def percentage_plan(
    *, name: str = "percentage-plan", rate: float = 0.025, minimum: int | None = None
) -> dict[str, object]:
    pricing: dict[str, object] = {"model": "percentage", "percentage_rate": scalar(rate)}
    if minimum is not None:
        pricing["minimum_fee"] = money(minimum)
    return {"name": name, "package_label": "Percentage", "pricing": pricing}


def recurring_payload() -> dict[str, object]:
    return {
        "mode": "recurring",
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "analysis_period": "month",
        "evaluation_horizon_periods": scalar(12, "reported"),
        "usage_unit_name": "active seat",
        "objective": {"metric": "contribution_after_fixed_costs"},
        "guardrails": {
            "max_active_customer_loss_rate": scalar(0.05, "reported"),
            "min_contribution_margin": scalar(0.60, "reported"),
            "max_weighted_average_price_increase_rate": scalar(0.25, "reported"),
            "max_manual_review_share": scalar(0.15, "reported"),
            "capacity_units_per_period": scalar(1_000, "reported"),
        },
        "current_fixed_costs_per_period": money(1_000_000, "reported"),
        "plans": [flat_plan("current-flat", 20_000), flat_plan("higher-flat", 25_000)],
        "segments": [
            {
                "name": "small-teams",
                "current_plan": "current-flat",
                "current_customers": scalar(100),
                "baseline_retention_rate": scalar(0.95, "reported"),
                "baseline_new_customers_per_period": scalar(10, "reported"),
                "usage_units_per_customer_per_period": scalar(8, "reported"),
                "billable_amount_per_customer_per_period": money(0),
                "current_quoted_charge_per_customer_per_period": money(0),
                "fixed_variable_cost_per_customer_per_period": money(2_000, "reported"),
                "variable_cost_per_usage_unit": money(500, "reported"),
            }
        ],
        "proposals": [
            {
                "name": "higher-flat-price",
                "validation_stage": "hypothesis",
                "change_summary": ["Raise flat price"],
                "incremental_fixed_costs_per_period": money(100_000, "estimated"),
                "one_time_implementation_costs": money(600_000, "estimated"),
                "assignments": [
                    {
                        "segment": "small-teams",
                        "target_plan": "higher-flat",
                        "migration_policy": "renewal",
                        "migration_share_within_horizon": scalar(0.80, "estimated"),
                        "manual_review_share": scalar(0.10, "reported"),
                        "retention_rate_after_migration": scalar(0.90, "estimated"),
                        "new_customer_multiplier": scalar(1.10, "estimated"),
                        "usage_multiplier": scalar(1, "reported"),
                        "billable_amount_multiplier": scalar(1, "reported"),
                        "variable_cost_multiplier": scalar(1, "reported"),
                        "transition_discount_rate": scalar(0.10, "estimated"),
                    }
                ],
            }
        ],
        "sensitivity_cases": [],
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_money_encoded_as_zero(self) -> None:
        payload = recurring_payload()
        payload["plans"][0]["pricing"]["flat_fee"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(payload)

    def test_rejects_unknown_scalar_encoded_as_zero(self) -> None:
        payload = recurring_payload()
        payload["segments"][0]["baseline_retention_rate"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown value must be null"):
            calculate(payload)

    def test_rejects_migration_and_review_shares_above_one(self) -> None:
        payload = recurring_payload()
        payload["proposals"][0]["assignments"][0]["manual_review_share"] = scalar(0.30)
        with self.assertRaisesRegex(ValueError, "migration and manual-review shares"):
            calculate(payload)

    def test_rejects_invalid_date_currency_and_mixed_currency(self) -> None:
        payload = recurring_payload()
        payload["as_of_date"] = "2026-02-30"
        with self.assertRaisesRegex(ValueError, "ISO date"):
            calculate(payload)

        payload = recurring_payload()
        payload["currency"] = "yen"
        with self.assertRaisesRegex(ValueError, "three-letter"):
            calculate(payload)

        payload = recurring_payload()
        payload["plans"][0]["pricing"]["flat_fee"] = money(20_000, currency="USD")
        with self.assertRaisesRegex(ValueError, "currency must match"):
            calculate(payload)

    def test_rejects_negative_rate_and_fractional_customers(self) -> None:
        payload = recurring_payload()
        payload["segments"][0]["usage_units_per_customer_per_period"] = scalar(-1)
        with self.assertRaisesRegex(ValueError, "must be nonnegative"):
            calculate(payload)

        payload = recurring_payload()
        payload["segments"][0]["baseline_retention_rate"] = scalar(1.01)
        with self.assertRaisesRegex(ValueError, "from 0 through 1"):
            calculate(payload)

        payload = recurring_payload()
        payload["segments"][0]["current_customers"] = scalar(1.5)
        with self.assertRaisesRegex(ValueError, "whole number"):
            calculate(payload)

    def test_rejects_duplicate_names_and_unknown_plan(self) -> None:
        for collection in ("plans", "segments", "proposals"):
            with self.subTest(collection=collection):
                payload = recurring_payload()
                payload[collection].append(copy.deepcopy(payload[collection][0]))
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    calculate(payload)

        payload = recurring_payload()
        payload["segments"][0]["current_plan"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown current plan"):
            calculate(payload)

    def test_rejects_missing_or_duplicate_segment_assignment(self) -> None:
        payload = recurring_payload()
        payload["proposals"][0]["assignments"] = []
        with self.assertRaisesRegex(ValueError, "exactly one assignment"):
            calculate(payload)

        payload = recurring_payload()
        assignment = copy.deepcopy(payload["proposals"][0]["assignments"][0])
        payload["proposals"][0]["assignments"].append(assignment)
        with self.assertRaisesRegex(ValueError, "duplicate assignment"):
            calculate(payload)

    def test_rejects_incompatible_migration_policies(self) -> None:
        payload = recurring_payload()
        assignment = payload["proposals"][0]["assignments"][0]
        assignment["migration_policy"] = "grandfathered"
        with self.assertRaisesRegex(ValueError, "grandfathered requires zero migration share"):
            calculate(payload)

        payload = recurring_payload()
        assignment = payload["proposals"][0]["assignments"][0]
        assignment["migration_policy"] = "manual_review"
        assignment["manual_review_share"] = scalar(0)
        with self.assertRaisesRegex(ValueError, "manual_review requires"):
            calculate(payload)

    def test_rejects_invalid_objective_and_formula_fields(self) -> None:
        payload = recurring_payload()
        payload["objective"]["metric"] = "cash_runway"
        with self.assertRaisesRegex(ValueError, "unsupported objective"):
            calculate(payload)

        payload = recurring_payload()
        payload["plans"][0]["pricing"]["percentage_rate"] = scalar(0.02)
        with self.assertRaisesRegex(ValueError, "unsupported pricing fields"):
            calculate(payload)

    def test_requires_quotes_for_current_and_target_quoted_plans(self) -> None:
        payload = recurring_payload()
        payload["plans"].append(
            {"name": "quoted", "package_label": "Quoted", "pricing": {"model": "quoted"}}
        )
        payload["segments"][0]["current_plan"] = "quoted"
        del payload["segments"][0]["current_quoted_charge_per_customer_per_period"]
        with self.assertRaisesRegex(ValueError, "current quoted charge"):
            calculate(payload)

        payload = recurring_payload()
        payload["plans"].append(
            {"name": "quoted", "package_label": "Quoted", "pricing": {"model": "quoted"}}
        )
        payload["proposals"][0]["assignments"][0]["target_plan"] = "quoted"
        with self.assertRaisesRegex(ValueError, "quoted charge"):
            calculate(payload)


class ChargeFormulaTests(unittest.TestCase):
    def test_flat_and_quoted_charges(self) -> None:
        self.assertEqual(
            calculate_charge(
                flat_plan("flat", 20_000),
                usage=None,
                billable_amount=None,
                quoted_charge=None,
                currency="JPY",
            ),
            20_000,
        )
        quoted = {"name": "quoted", "package_label": "Quoted", "pricing": {"model": "quoted"}}
        self.assertEqual(
            calculate_charge(
                quoted,
                usage=None,
                billable_amount=None,
                quoted_charge=Decimal("80000"),
                currency="JPY",
            ),
            80_000,
        )

    def test_base_plus_usage_applies_included_units_and_bounds(self) -> None:
        plan = usage_plan(base=10_000, included=5, excess=2_000, minimum=10_000, maximum=20_000)
        self.assertEqual(
            calculate_charge(
                plan,
                usage=Decimal("8"),
                billable_amount=None,
                quoted_charge=None,
                currency="JPY",
            ),
            16_000,
        )
        self.assertEqual(
            calculate_charge(
                plan,
                usage=Decimal("20"),
                billable_amount=None,
                quoted_charge=None,
                currency="JPY",
            ),
            20_000,
        )

    def test_percentage_uses_declared_billable_base(self) -> None:
        plan = percentage_plan(rate=0.025, minimum=5_000)
        self.assertEqual(
            calculate_charge(
                plan,
                usage=None,
                billable_amount=Decimal("400000"),
                quoted_charge=None,
                currency="JPY",
            ),
            10_000,
        )

    def test_missing_required_basis_and_unknown_cap_are_indeterminate(self) -> None:
        self.assertEqual(
            calculate_charge(
                usage_plan(), usage=None, billable_amount=None, quoted_charge=None, currency="JPY"
            ),
            "indeterminate",
        )
        plan = usage_plan()
        plan["pricing"]["maximum_fee"] = money(None, "unknown")
        self.assertEqual(
            calculate_charge(
                plan,
                usage=Decimal("8"),
                billable_amount=None,
                quoted_charge=None,
                currency="JPY",
            ),
            "indeterminate",
        )


if __name__ == "__main__":
    unittest.main()
