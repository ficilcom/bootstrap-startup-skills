from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/finance/working-capital-cycle-review/scripts/analyze_working_capital.py"


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "measurement_days": 30,
        "balance_basis": "average",
        "revenue": money(1_200_000),
        "cost_of_goods_sold": money(600_000),
        "accounts_receivable": money(400_000),
        "inventory": money(300_000),
        "accounts_payable": money(200_000),
        "customer_deposits": money(100_000),
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["targets"] = {"dso_days": scalar(8, "estimated"), "dio_days": scalar(12, "estimated"), "dpo_days": scalar(12, "estimated"), "customer_deposits": money(150_000, "estimated")}
    data["scenarios"] = [{"id": "slow-collections", "revenue": money(1_200_000), "cost_of_goods_sold": money(600_000), "accounts_receivable": money(600_000, "estimated"), "inventory": money(300_000), "accounts_payable": money(200_000), "customer_deposits": money(100_000)}]
    return data


def run_cli(data: object) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class WorkingCapitalTests(unittest.TestCase):
    def test_calculates_cycle_metrics_and_net_working_capital(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("base_metrics", result)
        metrics = result["base_metrics"]
        self.assertEqual(metrics["dso_days"], 10)
        self.assertEqual(metrics["dio_days"], 15)
        self.assertEqual(metrics["dpo_days"], 10)
        self.assertEqual(metrics["cash_conversion_cycle_days"], 15)
        self.assertEqual(metrics["net_working_capital"], 400_000)

    def test_advanced_targets_calculate_signed_cash_release_components(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("cash_release_components", result)
        release = result["cash_release_components"]
        self.assertEqual(release["receivables"], 80_000)
        self.assertEqual(release["inventory"], 60_000)
        self.assertEqual(release["payables"], 40_000)
        self.assertEqual(release["customer_deposits"], 50_000)
        self.assertEqual(release["total"], 230_000)

    def test_scenario_recalculates_cycle_without_changing_base(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("scenario_metrics", result)
        scenario = result["scenario_metrics"][0]
        self.assertEqual(scenario["id"], "slow-collections")
        self.assertEqual(scenario["dso_days"], 15)
        self.assertEqual(scenario["cash_conversion_cycle_days"], 20)
        self.assertEqual(scenario["net_working_capital"], 600_000)
        self.assertEqual(result["base_metrics"]["dso_days"], 10)

    def test_zero_revenue_only_makes_dso_and_ccc_indeterminate(self) -> None:
        data = payload()
        data["revenue"] = money(0)
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("base_metrics", result)
        metrics = result["base_metrics"]
        self.assertIsNone(metrics["dso_days"])
        self.assertEqual(metrics["dio_days"], 15)
        self.assertEqual(metrics["dpo_days"], 10)
        self.assertIsNone(metrics["cash_conversion_cycle_days"])
        self.assertEqual(metrics["net_working_capital"], 400_000)
        self.assertIn("zero_revenue_base", result["analysis_quality"]["warnings"])

    def test_unknown_inventory_is_local_and_unknown_target_keeps_other_release_values(self) -> None:
        data = advanced_payload()
        data["inventory"] = money(None, "unknown")
        data["targets"]["dso_days"] = scalar(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("base_metrics", result)
        self.assertEqual(result["base_metrics"]["dso_days"], 10)
        self.assertIsNone(result["base_metrics"]["dio_days"])
        self.assertEqual(result["base_metrics"]["dpo_days"], 10)
        release = result["cash_release_components"]
        self.assertIsNone(release["receivables"])
        self.assertIsNone(release["inventory"])
        self.assertEqual(release["payables"], 40_000)
        self.assertEqual(release["customer_deposits"], 50_000)
        self.assertIsNone(release["total"])

    def test_negative_release_is_preserved_as_cash_consumption(self) -> None:
        data = advanced_payload()
        data["targets"]["dso_days"] = scalar(12)
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("cash_release_components", result)
        self.assertEqual(result["cash_release_components"]["receivables"], -80_000)

    def test_rejects_duplicate_scenarios_bad_currency_basis_days_unknown_zero_and_mode(self) -> None:
        data = advanced_payload()
        data["scenarios"].append(dict(data["scenarios"][0]))
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["inventory"]["currency"] = "USD"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["balance_basis"] = "guess"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["measurement_days"] = 0
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["accounts_receivable"] = money(0, "unknown")
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["analysis_mode"] = "deep"
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
