#!/usr/bin/env python3
"""Tests for the deterministic pricing decision calculator."""

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
SCRIPT = ROOT / "skills/finance/pricing-decision/scripts/calculate_pricing_decision.py"
PRICING_MODULE = runpy.run_path(str(SCRIPT))
calculate = PRICING_MODULE["calculate"]
calculate_charge = PRICING_MODULE["calculate_charge"]
calculate_price_burden = PRICING_MODULE["calculate_price_burden"]
main = PRICING_MODULE["main"]


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


class CurrentEconomicsTests(unittest.TestCase):
    def test_calculates_current_counterfactual(self) -> None:
        current = calculate(recurring_payload())["current"]

        self.assertEqual(current["metrics"]["active_customers"], 105)
        self.assertEqual(current["metrics"]["revenue"], 2_100_000)
        self.assertEqual(current["metrics"]["contribution_profit"], 1_470_000)
        self.assertEqual(current["metrics"]["contribution_after_fixed_costs"], 470_000)
        self.assertEqual(current["metrics"]["contribution_margin"], Decimal("0.7"))
        self.assertEqual(current["metrics"]["arpa"], 20_000)
        self.assertEqual(current["metrics"]["total_usage_units"], 840)
        self.assertEqual(current["metrics"]["capacity_status"], "within_capacity")

    def test_percentage_and_quoted_current_plans(self) -> None:
        payload = recurring_payload()
        payload["plans"].append(percentage_plan(name="current-percentage", rate=0.025))
        segment = payload["segments"][0]
        segment["current_plan"] = "current-percentage"
        segment["billable_amount_per_customer_per_period"] = money(400_000)
        current = calculate(payload)["current"]
        self.assertEqual(current["segments"][0]["current_charge"], 10_000)

        payload = recurring_payload()
        payload["plans"].append(
            {"name": "current-quoted", "package_label": "Quoted", "pricing": {"model": "quoted"}}
        )
        segment = payload["segments"][0]
        segment["current_plan"] = "current-quoted"
        segment["current_quoted_charge_per_customer_per_period"] = money(50_000)
        current = calculate(payload)["current"]
        self.assertEqual(current["segments"][0]["current_charge"], 50_000)

    def test_zero_revenue_has_typed_rates(self) -> None:
        payload = recurring_payload()
        payload["plans"][0]["pricing"]["flat_fee"] = money(0)

        metrics = calculate(payload)["current"]["metrics"]

        self.assertEqual(metrics["revenue"], 0)
        self.assertEqual(metrics["contribution_margin"], "indeterminate_zero_revenue")
        self.assertEqual(metrics["arpa"], 0)

    def test_unknown_baseline_retention_is_not_zero(self) -> None:
        payload = recurring_payload()
        payload["segments"][0]["baseline_retention_rate"] = scalar(None, "unknown")

        current = calculate(payload)["current"]

        self.assertEqual(current["metrics"]["active_customers"], "indeterminate")
        self.assertEqual(current["metrics"]["revenue"], "indeterminate")
        self.assertTrue(
            any(path.endswith("baseline_retention_rate") for path in current["missing_inputs"])
        )


class ProposalEconomicsTests(unittest.TestCase):
    def test_calculates_migration_and_proposal_financials(self) -> None:
        proposal = calculate(recurring_payload())["proposals"][0]
        segment = proposal["segments"][0]

        self.assertEqual(segment["migration_cohort"], 80)
        self.assertEqual(segment["migrated_retained_customers"], 72)
        self.assertEqual(segment["migration_losses"], 8)
        self.assertEqual(segment["legacy_retained_customers"], 19)
        self.assertEqual(segment["new_customers"], 11)
        self.assertEqual(segment["manual_review_customers"], 10)
        self.assertEqual(segment["effective_migrated_charge"], 22_500)
        self.assertEqual(segment["target_new_customer_charge"], 25_000)
        self.assertEqual(proposal["metrics"]["active_customers"], 102)
        self.assertEqual(proposal["metrics"]["revenue"], 2_275_000)
        self.assertEqual(proposal["metrics"]["contribution_profit"], 1_663_000)
        self.assertEqual(proposal["metrics"]["contribution_after_fixed_costs"], 563_000)
        self.assertEqual(proposal["deltas"]["contribution_after_fixed_costs"], 93_000)
        self.assertEqual(proposal["one_time_implementation_costs"], 600_000)

    def test_grandfathered_customers_remain_on_legacy_price(self) -> None:
        payload = recurring_payload()
        assignment = payload["proposals"][0]["assignments"][0]
        assignment["migration_policy"] = "grandfathered"
        assignment["migration_share_within_horizon"] = scalar(0)
        assignment["manual_review_share"] = scalar(0)

        segment = calculate(payload)["proposals"][0]["segments"][0]

        self.assertEqual(segment["migrated_retained_customers"], 0)
        self.assertEqual(segment["legacy_retained_customers"], 95)
        self.assertEqual(segment["legacy_revenue"], 1_900_000)
        self.assertEqual(segment["new_revenue"], 275_000)

    def test_usage_and_cost_multipliers_change_target_economics(self) -> None:
        payload = recurring_payload()
        payload["plans"].append(usage_plan(name="target-usage"))
        assignment = payload["proposals"][0]["assignments"][0]
        assignment["target_plan"] = "target-usage"
        assignment["usage_multiplier"] = scalar(1.25)
        assignment["variable_cost_multiplier"] = scalar(1.10)

        segment = calculate(payload)["proposals"][0]["segments"][0]

        self.assertEqual(segment["proposal_usage_units_per_customer"], 10)
        self.assertEqual(segment["target_new_customer_charge"], 20_000)
        self.assertEqual(segment["effective_migrated_charge"], 18_000)
        self.assertEqual(segment["proposal_variable_cost_per_customer"], 7_700)

    def test_quoted_target_uses_assignment_quote(self) -> None:
        payload = recurring_payload()
        payload["plans"].append(
            {"name": "target-quoted", "package_label": "Quoted", "pricing": {"model": "quoted"}}
        )
        assignment = payload["proposals"][0]["assignments"][0]
        assignment["target_plan"] = "target-quoted"
        assignment["quoted_charge_per_customer_per_period"] = money(30_000)

        segment = calculate(payload)["proposals"][0]["segments"][0]

        self.assertEqual(segment["target_new_customer_charge"], 30_000)
        self.assertEqual(segment["effective_migrated_charge"], 27_000)

    def test_unknown_migration_retention_makes_proposal_indeterminate(self) -> None:
        payload = recurring_payload()
        payload["proposals"][0]["assignments"][0]["retention_rate_after_migration"] = scalar(
            None, "unknown"
        )

        proposal = calculate(payload)["proposals"][0]

        self.assertEqual(proposal["metrics"]["active_customers"], "indeterminate")
        self.assertEqual(proposal["metrics"]["revenue"], "indeterminate")
        self.assertTrue(
            any(path.endswith("retention_rate_after_migration") for path in proposal["missing_inputs"])
        )


class PriceBurdenTests(unittest.TestCase):
    def test_calculates_weighted_existing_customer_burden(self) -> None:
        burden = calculate(recurring_payload())["proposals"][0]["price_burden"]

        self.assertEqual(burden["weighted_average_increase_rate"], Decimal("0.125"))
        self.assertEqual(burden["weighted_median_increase_rate"], Decimal("0.125"))
        self.assertEqual(burden["bands"]["10_to_25_percent"]["customers"], 72)

    def test_assigns_all_price_change_bands(self) -> None:
        segments = [
            {
                "name": name,
                "current_charge": Decimal("100"),
                "effective_migrated_charge": Decimal(str(target)),
                "migrated_retained_customers": Decimal("1"),
            }
            for name, target in (
                ("decrease", 90),
                ("same", 100),
                ("small", 105),
                ("medium", 120),
                ("large", 140),
                ("very-large", 160),
            )
        ]

        burden = calculate_price_burden(segments)

        self.assertEqual(burden["bands"]["decrease"]["customers"], 1)
        self.assertEqual(burden["bands"]["unchanged"]["customers"], 1)
        self.assertEqual(burden["bands"]["0_to_10_percent"]["customers"], 1)
        self.assertEqual(burden["bands"]["10_to_25_percent"]["customers"], 1)
        self.assertEqual(burden["bands"]["25_to_50_percent"]["customers"], 1)
        self.assertEqual(burden["bands"]["over_50_percent"]["customers"], 1)

    def test_zero_current_price_is_excluded_from_percentage_burden(self) -> None:
        payload = recurring_payload()
        payload["plans"][0]["pricing"]["flat_fee"] = money(0)

        proposal = calculate(payload)["proposals"][0]
        segment = proposal["segments"][0]

        self.assertEqual(segment["price_change_amount"], 22_500)
        self.assertEqual(segment["price_change_rate"], "not_meaningful_zero_current_price")
        self.assertEqual(proposal["price_burden"]["excluded_zero_current_price_customers"], 72)
        self.assertEqual(proposal["price_burden"]["weighted_average_increase_rate"], "indeterminate")


class DecisionTests(unittest.TestCase):
    def test_hypothesis_with_improving_objective_requires_pilot(self) -> None:
        result = calculate(recurring_payload())["proposals"][0]

        self.assertEqual(result["objective"]["delta"], 93_000)
        self.assertEqual(result["decision_status"], "pilot_first")
        self.assertIn("validation_required", result["decision_reasons"])

    def test_validated_proposal_with_passing_guardrails_is_candidate(self) -> None:
        payload = recurring_payload()
        payload["proposals"][0]["validation_stage"] = "validated"

        result = calculate(payload)["proposals"][0]

        self.assertEqual(result["decision_status"], "candidate_for_rollout")
        self.assertEqual(set(result["guardrails"].values()), {"passed"})

    def test_each_financial_guardrail_can_reject_an_improving_proposal(self) -> None:
        cases = {
            "max_weighted_average_price_increase_rate": scalar(0.10),
            "min_contribution_margin": scalar(0.80),
            "max_active_customer_loss_rate": scalar(0.02),
            "max_manual_review_share": scalar(0.05),
            "capacity_units_per_period": scalar(800),
        }
        for field, threshold in cases.items():
            with self.subTest(field=field):
                payload = recurring_payload()
                payload["guardrails"][field] = threshold

                result = calculate(payload)["proposals"][0]

                self.assertEqual(result["guardrails"][field], "violated")
                self.assertEqual(result["decision_status"], "reject_under_assumptions")
                self.assertIn(f"guardrail_violated:{field}", result["decision_reasons"])

    def test_nonimproving_objective_is_rejected(self) -> None:
        payload = recurring_payload()
        payload["objective"] = {"metric": "active_customers"}

        result = calculate(payload)["proposals"][0]

        self.assertEqual(result["objective"]["delta"], -3)
        self.assertEqual(result["decision_status"], "reject_under_assumptions")
        self.assertIn("objective_not_improved", result["decision_reasons"])

    def test_missing_objective_or_critical_response_holds_for_evidence(self) -> None:
        payload = recurring_payload()
        del payload["objective"]
        result = calculate(payload)["proposals"][0]
        self.assertEqual(result["decision_status"], "hold_for_evidence")
        self.assertIn("objective_not_selected", result["decision_reasons"])

        payload = recurring_payload()
        payload["proposals"][0]["assignments"][0]["retention_rate_after_migration"] = scalar(
            None, "unknown"
        )
        result = calculate(payload)["proposals"][0]
        self.assertEqual(result["decision_status"], "hold_for_evidence")
        self.assertIn("critical_response_unknown", result["decision_reasons"])

    def test_unknown_supplied_guardrail_is_unassessed(self) -> None:
        payload = recurring_payload()
        payload["guardrails"]["max_active_customer_loss_rate"] = scalar(None, "unknown")

        result = calculate(payload)["proposals"][0]

        self.assertEqual(result["guardrails"]["max_active_customer_loss_rate"], "unassessed")
        self.assertEqual(result["decision_status"], "hold_for_evidence")

    def test_omitted_guardrails_do_not_create_universal_thresholds(self) -> None:
        payload = recurring_payload()
        payload["guardrails"] = {}

        result = calculate(payload)["proposals"][0]

        self.assertEqual(result["guardrails"], {})
        self.assertEqual(result["decision_status"], "pilot_first")


class SensitivityTests(unittest.TestCase):
    def test_rejects_invalid_sensitivity_cases(self) -> None:
        base_case = {
            "name": "retention-downside",
            "source_proposal": "higher-flat-price",
            "overrides": {
                "assignments.small-teams.retention_rate_after_migration": scalar(0.82, "estimated")
            },
        }
        payload = recurring_payload()
        payload["sensitivity_cases"] = [base_case, copy.deepcopy(base_case)]
        with self.assertRaisesRegex(ValueError, "duplicate sensitivity name"):
            calculate(payload)

        payload = recurring_payload()
        payload["sensitivity_cases"] = [copy.deepcopy(base_case)]
        payload["sensitivity_cases"][0]["source_proposal"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown source proposal"):
            calculate(payload)

        payload = recurring_payload()
        payload["sensitivity_cases"] = [copy.deepcopy(base_case)]
        payload["sensitivity_cases"][0]["overrides"] = {
            "assignments.missing.retention_rate_after_migration": scalar(0.82)
        }
        with self.assertRaisesRegex(ValueError, "unknown segment"):
            calculate(payload)

        for path in ("validation_stage", "assignments.small-teams.target_plan", "objective.metric"):
            with self.subTest(path=path):
                payload = recurring_payload()
                payload["sensitivity_cases"] = [copy.deepcopy(base_case)]
                payload["sensitivity_cases"][0]["overrides"] = {path: "changed"}
                with self.assertRaisesRegex(ValueError, "unsupported sensitivity override path"):
                    calculate(payload)

    def test_revalidates_typed_overrides_and_share_constraints(self) -> None:
        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "untyped",
                "source_proposal": "higher-flat-price",
                "overrides": {
                    "assignments.small-teams.retention_rate_after_migration": 0.82
                },
            }
        ]
        with self.assertRaisesRegex(ValueError, "must be an object"):
            calculate(payload)

        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "too-many",
                "source_proposal": "higher-flat-price",
                "overrides": {
                    "assignments.small-teams.manual_review_share": scalar(0.30)
                },
            }
        ]
        with self.assertRaisesRegex(ValueError, "migration and manual-review shares"):
            calculate(payload)

    def test_cases_recalculate_independently_and_report_changes(self) -> None:
        payload = recurring_payload()
        payload["sensitivity_cases"] = [
            {
                "name": "retention-downside",
                "source_proposal": "higher-flat-price",
                "overrides": {
                    "assignments.small-teams.retention_rate_after_migration": scalar(
                        0.82, "estimated"
                    )
                },
            },
            {
                "name": "usage-upside",
                "source_proposal": "higher-flat-price",
                "overrides": {
                    "assignments.small-teams.usage_multiplier": scalar(1.25, "estimated")
                },
            },
        ]

        result = calculate(payload)
        source = result["proposals"][0]
        downside, upside = result["sensitivity_cases"]

        self.assertEqual(downside["source_proposal"], "higher-flat-price")
        self.assertLess(downside["metrics"]["active_customers"], source["metrics"]["active_customers"])
        self.assertEqual(upside["segments"][0]["retention_rate_after_migration"], Decimal("0.90"))
        self.assertIn("active_customers", downside["deltas_from_source"])
        self.assertIn(
            "max_active_customer_loss_rate", downside["added_guardrail_violations"]
        )
        self.assertIn(
            "guardrail_violated:max_active_customer_loss_rate",
            downside["added_decision_reasons"],
        )
        self.assertIn("validation_required", downside["removed_decision_reasons"])


class CliTests(unittest.TestCase):
    def test_reads_valid_file_and_standard_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pricing.json"
            path.write_text(json.dumps(recurring_payload()), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main([str(path)])
        self.assertEqual(status, 0)
        self.assertNotIn("\n ", stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["proposals"][0]["decision_status"], "pilot_first")

        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(recurring_payload()))), redirect_stdout(stdout):
            status = main(["-"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["mode"], "recurring")

    def test_file_json_and_validation_errors_return_two(self) -> None:
        cases = [
            (["/tmp/pricing-decision-file-that-does-not-exist.json"], None),
            (["-"], "{"),
            (["-"], json.dumps({"mode": "hybrid"})),
        ]
        for argv, stdin_value in cases:
            with self.subTest(argv=argv, stdin_value=stdin_value):
                stdout = io.StringIO()
                stderr = io.StringIO()
                context = (
                    patch("sys.stdin", io.StringIO(stdin_value))
                    if stdin_value is not None
                    else patch("sys.stdin", io.StringIO(""))
                )
                with context, redirect_stdout(stdout), redirect_stderr(stderr):
                    status = main(argv)
                self.assertEqual(status, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertTrue(stderr.getvalue().startswith("error: "))
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
