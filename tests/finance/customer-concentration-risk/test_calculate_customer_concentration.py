#!/usr/bin/env python3
"""Tests for the deterministic customer-concentration calculator."""

from __future__ import annotations

import copy
import io
import json
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/finance/customer-concentration-risk/scripts/calculate_customer_concentration.py"
MODULE = runpy.run_path(str(SCRIPT))
calculate = MODULE["calculate"]
main = MODULE["main"]


def money(amount: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-22",
        "analysis_period": "2026-07",
        "currency": "JPY",
        "revenue_basis": "recognized_net_revenue",
        "customers": [
            {
                "id": "customer-a",
                "revenue": money(600_000),
                "gross_profit": money(360_000),
                "cash_collections": money(500_000),
            },
            {
                "id": "customer-b",
                "revenue": money(250_000, "reported"),
                "gross_profit": money(125_000, "estimated"),
                "cash_collections": money(300_000),
            },
            {
                "id": "customer-c",
                "revenue": money(150_000),
                "gross_profit": money(60_000),
                "cash_collections": money(200_000),
            },
        ],
        "financial_context": {
            "opening_available_cash": money(3_000_000),
            "minimum_cash_buffer": money(1_000_000, "reported"),
            "baseline_monthly_net_cash_flow": money(-200_000, "estimated"),
            "fixed_costs": money(700_000),
        },
        "scenarios": [
            {
                "id": "customer-a-churn",
                "customer_id": "customer-a",
                "event": "churn",
                "reduction_rate": 1,
                "cash_impact_now": money(500_000, "reported"),
                "recurring_monthly_cash_impact": money(500_000, "estimated"),
            }
        ],
    }


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_value_encoded_as_zero(self) -> None:
        data = payload()
        data["customers"][0]["revenue"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "must be null when evidence is unknown"):
            calculate(data)

    def test_rejects_duplicate_customer_ids(self) -> None:
        data = payload()
        data["customers"].append(copy.deepcopy(data["customers"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate customer id"):
            calculate(data)

    def test_rejects_customer_currency_mismatch(self) -> None:
        data = payload()
        data["customers"][0]["revenue"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "must match top-level currency"):
            calculate(data)

    def test_rejects_negative_revenue(self) -> None:
        data = payload()
        data["customers"][0]["revenue"] = money(-1)
        with self.assertRaisesRegex(ValueError, "must be nonnegative"):
            calculate(data)

    def test_rejects_payment_delay_with_reduction_rate(self) -> None:
        data = payload()
        scenario = data["scenarios"][0]
        scenario["event"] = "payment_delay"
        with self.assertRaisesRegex(ValueError, "not valid for payment_delay"):
            calculate(data)

    def test_rejects_unknown_scenario_customer(self) -> None:
        data = payload()
        data["scenarios"][0]["customer_id"] = "not-present"
        with self.assertRaisesRegex(ValueError, "must reference a known customer"):
            calculate(data)

    def test_rejects_invalid_reduction_rate(self) -> None:
        data = payload()
        data["scenarios"][0]["reduction_rate"] = 1.01
        with self.assertRaisesRegex(ValueError, "must be from 0 through 1"):
            calculate(data)


class ConcentrationTests(unittest.TestCase):
    def test_calculates_top_shares_and_hhi_for_each_metric(self) -> None:
        result = calculate(payload())
        revenue = result["concentration"]["revenue"]
        gross_profit = result["concentration"]["gross_profit"]
        cash = result["concentration"]["cash_collections"]

        self.assertEqual(revenue["status"], "calculated")
        self.assertEqual(revenue["total"], Decimal("1000000"))
        self.assertEqual(revenue["top_n_shares"]["1"], Decimal("0.6"))
        self.assertEqual(revenue["top_n_shares"]["3"], Decimal("1"))
        self.assertEqual(revenue["top_n_shares"]["10"], Decimal("1"))
        self.assertEqual(revenue["hhi"], Decimal("4450.00"))
        self.assertEqual(revenue["customer_shares"][0]["customer_id"], "customer-a")
        self.assertEqual(gross_profit["hhi"], Decimal("5010.520999915832000673343995"))
        self.assertEqual(cash["top_n_shares"]["1"], Decimal("0.5"))
        self.assertFalse(result["provisional"])

    def test_unknown_customer_metric_does_not_create_partial_ratio(self) -> None:
        data = payload()
        data["customers"][2]["cash_collections"] = money(None, "unknown")

        cash = calculate(data)["concentration"]["cash_collections"]

        self.assertEqual(cash["status"], "indeterminate_missing_customer_values")
        self.assertEqual(cash["known_total"], Decimal("800000"))
        self.assertEqual(cash["missing_customer_ids"], ["customer-c"])
        self.assertIsNone(cash["top_n_shares"])

    def test_negative_customer_gross_profit_is_not_used_for_hhi(self) -> None:
        data = payload()
        data["customers"][2]["gross_profit"] = money(-10_000)

        gross_profit = calculate(data)["concentration"]["gross_profit"]

        self.assertEqual(gross_profit["status"], "indeterminate_negative_gross_profit")
        self.assertIsNone(gross_profit["hhi"])


class ScenarioTests(unittest.TestCase):
    def test_churn_calculates_profit_cash_buffer_runway_and_fixed_cost_coverage(self) -> None:
        scenario = calculate(payload())["scenarios"][0]

        self.assertEqual(scenario["revenue_lost"], Decimal("600000"))
        self.assertEqual(scenario["gross_profit_lost"], Decimal("360000"))
        self.assertEqual(scenario["gross_profit_after_event"], Decimal("185000"))
        self.assertEqual(scenario["fixed_cost_coverage_after_event"], Decimal("0.2642857142857142857142857143"))
        self.assertEqual(scenario["cash_after_event"], Decimal("2500000"))
        self.assertEqual(scenario["adjusted_monthly_net_cash_flow"], Decimal("-700000"))
        self.assertEqual(scenario["months_to_minimum_cash_buffer"], Decimal("2.142857142857142857142857143"))
        self.assertEqual(scenario["months_to_zero_cash"], Decimal("3.571428571428571428571428571"))
        self.assertEqual(scenario["missing_inputs"], [])

    def test_payment_delay_does_not_reduce_revenue_or_gross_profit(self) -> None:
        data = payload()
        data["scenarios"] = [
            {
                "id": "customer-a-delay",
                "customer_id": "customer-a",
                "event": "payment_delay",
                "cash_impact_now": money(1_700_000),
                "recurring_monthly_cash_impact": money(0),
            }
        ]

        scenario = calculate(data)["scenarios"][0]

        self.assertEqual(scenario["revenue_lost"], Decimal("0"))
        self.assertEqual(scenario["gross_profit_lost"], Decimal("0"))
        self.assertEqual(scenario["cash_after_event"], Decimal("1300000"))
        self.assertEqual(scenario["months_to_minimum_cash_buffer"], Decimal("1.5"))

    def test_missing_cash_inputs_remain_indeterminate(self) -> None:
        data = payload()
        data["financial_context"]["opening_available_cash"] = money(None, "unknown")

        scenario = calculate(data)["scenarios"][0]

        self.assertIsNone(scenario["cash_after_event"])
        self.assertIsNone(scenario["months_to_zero_cash"])
        self.assertIn("financial_context.opening_available_cash", scenario["missing_inputs"])

    def test_nonnegative_flow_does_not_invent_cash_exhaustion_date(self) -> None:
        data = payload()
        data["financial_context"]["baseline_monthly_net_cash_flow"] = money(100_000)
        data["scenarios"][0]["recurring_monthly_cash_impact"] = money(100_000)

        scenario = calculate(data)["scenarios"][0]

        self.assertEqual(scenario["months_to_minimum_cash_buffer"], "not_exhausted_under_constant_monthly_model")
        self.assertEqual(scenario["months_to_zero_cash"], "not_exhausted_under_constant_monthly_model")


class CliTests(unittest.TestCase):
    def test_main_writes_json_and_validation_errors_to_stderr(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["-"])
        self.assertEqual(code, 2)
        self.assertIn("error:", error.getvalue())

        data = json.dumps(payload())
        original_stdin = __import__("sys").stdin
        try:
            __import__("sys").stdin = io.StringIO(data)
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["-"])
        finally:
            __import__("sys").stdin = original_stdin
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["currency"], "JPY")


if __name__ == "__main__":
    unittest.main()
