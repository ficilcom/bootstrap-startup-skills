from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/sales/sales-deal-qualification/scripts/qualify_sales_deals.py"


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-28",
        "forecast_end_date": "2026-09-30",
        "currency": "JPY",
        "founder_intervention_threshold": money(500_000),
        "criteria": [{"id": "need", "importance": "must"}, {"id": "budget", "importance": "must"}, {"id": "champion", "importance": "should"}],
        "deals": [
            {"id": "deal-a", "customer_id": "customer-1", "amount": money(1_000_000, "reported"), "stage_probability": scalar(0.5, "reported"), "close_date": "2026-09-15", "next_action_date": "2026-08-29", "qualification_results": [{"id": "need", "status": "verified"}, {"id": "budget", "status": "verified"}, {"id": "champion", "status": "reported"}]},
            {"id": "deal-b", "customer_id": "customer-2", "amount": money(300_000, "reported"), "stage_probability": scalar(0.3, "reported"), "close_date": "2026-09-20", "next_action_date": "2026-08-30", "qualification_results": [{"id": "need", "status": "failed"}, {"id": "budget", "status": "verified"}, {"id": "champion", "status": "unknown"}]},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["deals"][0].update({"decision_process_status": "unknown", "mutual_action_plan_status": "reported", "commercial_terms_status": "verified"})
    data["deals"][1].update({"decision_process_status": "failed", "mutual_action_plan_status": "unknown", "commercial_terms_status": "unknown"})
    return data


def run_cli(data: object) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class SalesDealQualificationTests(unittest.TestCase):
    def test_core_separates_weighted_value_from_qualification_gates(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("deals", result)
        deals = {item["id"]: item for item in result["deals"]}
        self.assertEqual(deals["deal-a"]["weighted_amount"], 500_000)
        self.assertEqual(deals["deal-a"]["eligibility_status"], "qualified")
        self.assertEqual(deals["deal-a"]["recommended_action"], "continue")
        self.assertEqual(deals["deal-b"]["eligibility_status"], "disqualified")
        self.assertEqual(deals["deal-b"]["recommended_action"], "exit")
        self.assertEqual(result["weighted_order"], ["deal-a", "deal-b"])

    def test_unverified_must_gate_holds_small_deal_and_escalates_high_value_deal(self) -> None:
        data = payload()
        data["deals"][0]["qualification_results"][1]["status"] = "reported"
        data["deals"][1]["qualification_results"][0]["status"] = "unknown"
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("deals", result)
        deals = {item["id"]: item for item in result["deals"]}
        self.assertEqual(deals["deal-a"]["recommended_action"], "founder_intervention")
        self.assertEqual(deals["deal-b"]["recommended_action"], "hold")
        self.assertIn("budget", deals["deal-a"]["unverified_gates"])

    def test_advanced_checks_create_explicit_gates(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("deals", result)
        deals = {item["id"]: item for item in result["deals"]}
        self.assertEqual(deals["deal-a"]["eligibility_status"], "conditional")
        self.assertEqual(deals["deal-a"]["recommended_action"], "founder_intervention")
        self.assertIn("decision_process", deals["deal-a"]["unverified_gates"])
        self.assertIn("decision_process", deals["deal-b"]["failed_gates"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_timing_flags_do_not_rewrite_probability(self) -> None:
        data = payload()
        data["deals"][0]["close_date"] = "2026-08-20"
        data["deals"][0]["next_action_date"] = "2026-08-27"
        data["deals"][1]["close_date"] = "2026-10-01"
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("deals", result)
        deals = {item["id"]: item for item in result["deals"]}
        self.assertIn("close_date_overdue", deals["deal-a"]["timing_flags"])
        self.assertIn("next_action_overdue", deals["deal-a"]["timing_flags"])
        self.assertEqual(deals["deal-a"]["weighted_amount"], 500_000)
        self.assertIn("forecast_period_outside", deals["deal-b"]["timing_flags"])

    def test_unknown_probability_only_blocks_weighting_for_that_deal(self) -> None:
        data = payload()
        data["deals"][0]["stage_probability"] = scalar(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("deals", result)
        self.assertIsNone(result["deals"][0]["weighted_amount"])
        self.assertEqual(result["weighted_order"], ["deal-b"])
        self.assertIn("deals[0].stage_probability", result["analysis_quality"]["decision_changing_unknowns"])

    def test_rejects_duplicate_ids_unknown_criteria_and_duplicate_results(self) -> None:
        data = payload()
        data["deals"][1]["id"] = "deal-a"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["qualification_results"][0]["id"] = "missing"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["qualification_results"][1]["id"] = "need"
        self.assertEqual(run_cli(data).returncode, 2)

    def test_rejects_bad_dates_probability_status_currency_and_unknown_zero(self) -> None:
        data = payload()
        data["forecast_end_date"] = "2026-08-01"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["stage_probability"] = scalar(1.1)
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["qualification_results"][0]["status"] = "maybe"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["amount"]["currency"] = "USD"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["deals"][0]["amount"] = money(0, "unknown")
        self.assertEqual(run_cli(data).returncode, 2)

    def test_cli_reports_usage_and_malformed_json(self) -> None:
        usage = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)
        self.assertTrue(usage.stderr.startswith("usage: "))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{", encoding="utf-8")
            malformed = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
        self.assertEqual(malformed.returncode, 2)
        self.assertTrue(malformed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
