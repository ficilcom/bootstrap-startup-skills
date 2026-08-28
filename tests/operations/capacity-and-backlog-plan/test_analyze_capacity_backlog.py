from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/operations/capacity-and-backlog-plan/scripts/analyze_capacity_backlog.py"


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "period_unit": "week",
        "horizon_periods": 3,
        "periods": [
            {"period": 1, "internal_capacity_hours": scalar(40), "external_capacity_hours": scalar(0)},
            {"period": 2, "internal_capacity_hours": scalar(40), "external_capacity_hours": scalar(0)},
            {"period": 3, "internal_capacity_hours": scalar(40), "external_capacity_hours": scalar(0)},
        ],
        "work_items": [
            {"id": "committed-1", "due_period": 1, "commitment": "committed", "required_hours": scalar(30), "contribution": money(300_000, "reported")},
            {"id": "backlog-1", "due_period": 2, "commitment": "backlog", "required_hours": scalar(60), "contribution": money(600_000, "reported")},
            {"id": "qualified-1", "due_period": 3, "commitment": "qualified", "required_hours": scalar(50, "estimated"), "contribution": money(500_000, "estimated")},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["interventions"] = [{"id": "outsourcing", "type": "outsource", "start_period": 2, "capacity_hours_per_period": scalar(20, "reported"), "one_time_cost": money(10_000), "recurring_cost_per_period": money(5_000, "reported")}]
    data["scenarios"] = [{"id": "downside", "demand_factor": scalar(1.2, "estimated"), "capacity_factor": scalar(0.8, "estimated")}]
    return data


def run_cli(data: object) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class CapacityBacklogTests(unittest.TestCase):
    def test_calculates_period_and_cumulative_delivery_gaps(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("period_metrics", result)
        periods = {item["period"]: item for item in result["period_metrics"]}
        self.assertEqual(periods[1]["delivery_demand_hours"], 30)
        self.assertEqual(periods[2]["delivery_demand_hours"], 60)
        self.assertEqual(periods[2]["cumulative_delivery_gap_hours"], 10)
        self.assertEqual(result["first_delivery_breach_period"], 2)
        self.assertEqual(result["acceptance_gate"], "closed")
        self.assertEqual(result["at_risk_items"], ["backlog-1", "committed-1"])

    def test_qualified_demand_is_separate_from_delivery_commitments(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("period_metrics", result)
        period = result["period_metrics"][2]
        self.assertEqual(period["qualified_demand_hours"], 50)
        self.assertEqual(period["delivery_demand_hours"], 0)
        self.assertEqual(period["potential_demand_hours"], 50)

    def test_intervention_adds_capacity_and_reports_cost_without_authorizing_it(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("intervention_metrics", result)
        intervention = result["intervention_metrics"][0]
        self.assertEqual(intervention["id"], "outsourcing")
        self.assertEqual(intervention["total_added_capacity_hours"], 40)
        self.assertEqual(intervention["total_cost"], 20_000)
        self.assertIsNone(intervention["first_delivery_breach_period"])

    def test_downside_scenario_can_move_first_breach(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("scenario_metrics", result)
        scenario = result["scenario_metrics"][0]
        self.assertEqual(scenario["id"], "downside")
        self.assertEqual(scenario["first_delivery_breach_period"], 1)
        self.assertEqual(scenario["maximum_cumulative_delivery_gap_hours"], 44)

    def test_unknown_qualified_hours_does_not_erase_delivery_view(self) -> None:
        data = payload()
        data["work_items"][2]["required_hours"] = scalar(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("period_metrics", result)
        self.assertEqual(result["first_delivery_breach_period"], 2)
        self.assertIsNone(result["period_metrics"][2]["potential_demand_hours"])
        self.assertEqual(result["period_metrics"][2]["delivery_demand_hours"], 0)
        self.assertIn("work_items[2].required_hours", result["analysis_quality"]["decision_changing_unknowns"])

    def test_rejects_duplicate_ids_period_gaps_and_out_of_horizon_references(self) -> None:
        data = payload()
        data["work_items"][1]["id"] = "committed-1"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["periods"][1]["period"] = 3
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["work_items"][0]["due_period"] = 4
        self.assertEqual(run_cli(data).returncode, 2)
        data = advanced_payload()
        data["interventions"][0]["start_period"] = 4
        self.assertEqual(run_cli(data).returncode, 2)

    def test_rejects_bad_commitment_currency_unknown_zero_factor_and_mode(self) -> None:
        data = payload()
        data["work_items"][0]["commitment"] = "maybe"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["work_items"][0]["contribution"]["currency"] = "USD"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["periods"][0]["internal_capacity_hours"] = scalar(0, "unknown")
        self.assertEqual(run_cli(data).returncode, 2)
        data = advanced_payload()
        data["scenarios"][0]["capacity_factor"] = scalar(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        self.assertIsNone(json.loads(completed.stdout)["scenario_metrics"][0]["first_delivery_breach_period"])
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
