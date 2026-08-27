#!/usr/bin/env python3
"""Tests for the deterministic expense and SaaS audit calculator."""

from __future__ import annotations

import copy
import io
import json
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/finance/expense-and-saas-audit/scripts/calculate_expense_audit.py"
MODULE = runpy.run_path(str(SCRIPT))
calculate = MODULE["calculate"]
main = MODULE["main"]


def money(amount: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def expense() -> dict[str, object]:
    return {
        "id": "design-tool",
        "label": "Design tool",
        "category": "saas",
        "billing_cycle": "monthly",
        "proposed_billing_cycle": "monthly",
        "current_billing": money(3000),
        "proposed_billing": money(1000, "estimated"),
        "action": "rightsize_seats",
        "effective_date": "2026-09-01",
        "classification_signals": ["oversized"],
        "dependency_flags": [],
        "usage": {"purchased_seats": scalar(20), "active_seats": scalar(8), "unit_price": money(150)},
        "contracts": {
            "renewal_date": None,
            "cancellation_notice_days": None,
            "minimum_commitment_end_date": None,
        },
        "implementation_costs": {
            "termination_fee": money(0), "migration": money(0), "reconfiguration": money(0),
            "training": money(0), "lost_discount": money(0),
        },
        "implementation_effort": {
            "migration_hours": scalar(0), "reconfiguration_hours": scalar(2, "estimated"),
            "training_hours": scalar(0), "internal_hourly_cost": money(50, "reported"),
        },
    }


def payload() -> dict[str, object]:
    return {"as_of_date": "2026-08-22", "currency": "USD", "analysis_months": 12, "expenses": [expense()]}


class ValidationTests(unittest.TestCase):
    def test_unknown_must_not_be_encoded_as_zero(self) -> None:
        data = payload()
        data["expenses"][0]["current_billing"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
            calculate(data)

    def test_rejects_duplicate_expense_ids(self) -> None:
        data = payload()
        duplicate = copy.deepcopy(data["expenses"][0])
        data["expenses"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate expense id"):
            calculate(data)

    def test_rejects_active_seats_above_purchased_seats(self) -> None:
        data = payload()
        data["expenses"][0]["usage"]["active_seats"] = scalar(21)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            calculate(data)

    def test_rejects_mixed_currency(self) -> None:
        data = payload()
        data["expenses"][0]["current_billing"] = {"amount": 3000, "evidence": "confirmed", "currency": "EUR"}
        with self.assertRaisesRegex(ValueError, "match top-level"):
            calculate(data)

    def test_rejects_past_effective_date(self) -> None:
        data = payload()
        data["expenses"][0]["effective_date"] = "2026-08-21"
        with self.assertRaisesRegex(ValueError, "must not precede"):
            calculate(data)


class CalculationTests(unittest.TestCase):
    def test_rightsizing_reports_net_savings_and_is_safe_to_prepare(self) -> None:
        result = calculate(payload())
        candidate = result["candidates"][0]

        self.assertEqual(candidate["decision_state"], "safe_to_execute")
        self.assertEqual(candidate["usage"]["utilization_rate"], 0.4)
        self.assertEqual(candidate["usage"]["unit_price"], 150)
        self.assertEqual(candidate["savings"]["monthly_recurring"], 2000)
        self.assertEqual(candidate["savings"]["annual_recurring"], 24000)
        self.assertEqual(candidate["costs"]["labor_cost"], 100)
        self.assertEqual(candidate["savings"]["first_year_net"], 23900)
        self.assertEqual(result["execution_order"], ["design-tool"])
        self.assertIn("cancellation", result["authorization_required"])

    def test_annualization_uses_distinct_current_and_proposed_cycles(self) -> None:
        data = payload()
        item = data["expenses"][0]
        item["action"] = "annualize"
        item["current_billing"] = money(100)
        item["proposed_billing"] = money(1000)
        item["proposed_billing_cycle"] = "annual"

        candidate = calculate(data)["candidates"][0]

        self.assertEqual(candidate["costs"]["current_annual_cost"], 1200)
        self.assertEqual(candidate["costs"]["proposed_annual_cost"], 1000)
        self.assertEqual(candidate["savings"]["annual_recurring"], 200)

    def test_protected_dependency_is_not_a_cut_candidate(self) -> None:
        data = payload()
        data["expenses"][0]["dependency_flags"] = ["data_security", "revenue"]

        candidate = calculate(data)["candidates"][0]

        self.assertEqual(candidate["decision_state"], "do_not_cut")
        self.assertIn("protected_dependency:data_security,revenue", candidate["reasons"])
        self.assertEqual(calculate(data)["execution_order"], [])

    def test_unknown_implementation_cost_requires_validation_not_a_guess(self) -> None:
        data = payload()
        data["expenses"][0]["implementation_costs"]["migration"] = money(None, "unknown")

        result = calculate(data)
        candidate = result["candidates"][0]

        self.assertEqual(candidate["decision_state"], "validate_first")
        self.assertIsNone(candidate["savings"]["first_year_net"])
        self.assertTrue(result["totals_by_decision_state"]["validate_first"]["incomplete"])

    def test_contract_locked_without_terms_requires_validation(self) -> None:
        data = payload()
        item = data["expenses"][0]
        item["classification_signals"] = ["contract_locked", "renegotiable"]
        item["action"] = "renegotiate"

        candidate = calculate(data)["candidates"][0]

        self.assertEqual(candidate["decision_state"], "validate_first")
        self.assertIn("contract_terms_unknown", candidate["reasons"])

    def test_sso_api_dependency_requires_validation(self) -> None:
        data = payload()
        data["expenses"][0]["dependency_flags"] = ["sso_api_automation"]

        candidate = calculate(data)["candidates"][0]

        self.assertEqual(candidate["decision_state"], "validate_first")
        self.assertIn("sso_api_automation_dependency", candidate["reasons"])

    def test_execution_order_prioritizes_safe_then_notice_deadline(self) -> None:
        data = payload()
        second = copy.deepcopy(data["expenses"][0])
        second["id"] = "duplicate-tool"
        second["label"] = "Duplicate tool"
        second["action"] = "cancel"
        second["classification_signals"] = ["duplicate", "contract_locked"]
        second["contracts"] = {
            "renewal_date": "2026-10-01", "cancellation_notice_days": 15,
            "minimum_commitment_end_date": "2026-08-22",
        }
        data["expenses"].append(second)

        result = calculate(data)

        self.assertEqual(result["execution_order"], ["duplicate-tool", "design-tool"])
        self.assertEqual(result["candidates"][0]["notification_deadline"], "2026-09-16")


class CliTests(unittest.TestCase):
    def test_cli_returns_validation_error_with_exit_code_two(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
            code = main(["-"])

        self.assertEqual(code, 2)
        self.assertIn("error:", stderr.getvalue())

    def test_cli_writes_json(self) -> None:
        stdout = io.StringIO()
        original_stdin = __import__("sys").stdin
        try:
            __import__("sys").stdin = io.StringIO(json.dumps(payload()))
            with redirect_stdout(stdout):
                code = main(["-"])
        finally:
            __import__("sys").stdin = original_stdin

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["currency"], "USD")


if __name__ == "__main__":
    unittest.main()
