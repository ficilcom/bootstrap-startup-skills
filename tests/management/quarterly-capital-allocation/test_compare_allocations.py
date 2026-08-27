from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/management/quarterly-capital-allocation/scripts/compare_allocations.py"
SPEC = importlib.util.spec_from_file_location("compare_allocations", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "quarter_months": 3,
        "opening_cash": money(500_000),
        "minimum_cash_buffer": money(250_000, "reported"),
        "baseline_net_cash_by_month": [money(50_000), money(50_000), money(50_000)],
        "proposals": [
            {
                "name": "crm-improvement",
                "strategic_fit": "supports_priority",
                "reversibility": "medium",
                "upfront_cost": money(100_000),
                "monthly_costs": [money(20_000), money(20_000), money(20_000)],
                "base_benefits": [money(0, "estimated"), money(80_000, "estimated"), money(100_000, "estimated")],
                "downside_benefits": [money(0, "estimated"), money(20_000, "estimated"), money(40_000, "estimated")],
                "downside_extra_costs": [money(0, "estimated"), money(10_000, "estimated"), money(10_000, "estimated")],
                "dependencies": ["sales-owner"],
                "benefit_overlap_group": "revenue-operations",
            },
            {
                "name": "inventory-buffer",
                "strategic_fit": "required_guardrail",
                "reversibility": "low",
                "upfront_cost": money(200_000),
                "monthly_costs": [money(0), money(0), money(0)],
                "base_benefits": [money(100_000, "estimated"), money(100_000, "estimated"), money(100_000, "estimated")],
                "downside_benefits": [money(0, "estimated"), money(0, "estimated"), money(0, "estimated")],
                "downside_extra_costs": [money(0), money(0), money(0)],
                "dependencies": ["supplier-confirmation"],
                "benefit_overlap_group": "supply-continuity",
            },
        ],
        "portfolios": [
            {"name": "crm-only", "proposals": ["crm-improvement"]},
            {"name": "inventory-only", "proposals": ["inventory-buffer"]},
            {"name": "both", "proposals": ["crm-improvement", "inventory-buffer"]},
        ],
    }


class CapitalAllocationTests(unittest.TestCase):
    def test_calculates_proposal_base_downside_and_payback(self) -> None:
        result = MODULE.calculate(payload())
        proposals = {item["name"]: item for item in result["proposals"]}
        crm = proposals["crm-improvement"]

        self.assertEqual(crm["base"]["ending_cash"], 670_000)
        self.assertEqual(crm["base"]["minimum_cash"], 400_000)
        self.assertEqual(crm["base"]["net_cash_effect"], 20_000)
        self.assertEqual(crm["base"]["payback_month"], 3)
        self.assertEqual(crm["downside"]["ending_cash"], 530_000)
        self.assertEqual(crm["downside"]["net_cash_effect"], -120_000)
        self.assertIsNone(crm["downside"]["payback_month"])

    def test_portfolio_requires_base_and_downside_buffer(self) -> None:
        result = MODULE.calculate(payload())
        portfolios = {item["name"]: item for item in result["portfolios"]}

        self.assertTrue(portfolios["crm-only"]["affordable_in_base_and_downside"])
        self.assertTrue(portfolios["inventory-only"]["affordable_in_base_and_downside"])
        self.assertFalse(portfolios["both"]["affordable_in_base_and_downside"])
        self.assertEqual(portfolios["both"]["base"]["buffer_breach_month"], 0)
        self.assertEqual(result["affordable_portfolios"], ["inventory-only", "crm-only"])

    def test_unknown_proposal_input_makes_dependent_portfolio_indeterminate(self) -> None:
        data = payload()
        data["proposals"][0]["upfront_cost"] = money(None, "unknown")

        result = MODULE.calculate(data)
        proposals = {item["name"]: item for item in result["proposals"]}
        portfolios = {item["name"]: item for item in result["portfolios"]}

        self.assertEqual(proposals["crm-improvement"]["status"], "indeterminate")
        self.assertEqual(portfolios["crm-only"]["status"], "indeterminate")
        self.assertNotIn("crm-only", result["affordable_portfolios"])

    def test_overlap_group_is_flagged_without_silently_removing_benefits(self) -> None:
        data = payload()
        data["proposals"][1]["benefit_overlap_group"] = "revenue-operations"

        both = {item["name"]: item for item in MODULE.calculate(data)["portfolios"]}["both"]

        self.assertIn("benefit_overlap_requires_validation", both["flags"])

    def test_rejects_duplicate_proposals_unknown_references_and_duplicate_portfolio_members(self) -> None:
        data = payload()
        data["proposals"][1]["name"] = "crm-improvement"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["portfolios"][0]["proposals"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "known proposal"):
            MODULE.calculate(data)

        data = payload()
        data["portfolios"][0]["proposals"] = ["crm-improvement", "crm-improvement"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.calculate(data)

    def test_rejects_wrong_month_count_currency_and_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["proposals"][0]["monthly_costs"] = [money(1)]
        with self.assertRaisesRegex(ValueError, "quarter_months"):
            MODULE.calculate(data)

        data = payload()
        data["opening_cash"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["minimum_cash_buffer"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_output_refuses_to_call_quantified_order_an_optimum(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(
            result["comparison_scope"],
            "quantified cash resilience only; strategic fit, option value, dependencies, and unpriced benefits remain separate",
        )

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertIn("crm-only", json.loads(completed.stdout)["affordable_portfolios"])

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
