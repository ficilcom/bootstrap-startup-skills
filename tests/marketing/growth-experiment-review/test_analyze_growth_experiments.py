from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/marketing/growth-experiment-review/scripts/analyze_growth_experiments.py"


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "horizon_weeks": 4,
        "internal_hourly_cost": money(5_000),
        "weekly_execution_capacity_hours": scalar(20, "reported"),
        "experiments": [
            {"id": "pricing-page", "status": "proposed", "cash_cost": money(100_000), "effort_hours": scalar(10, "estimated"), "potential_gross_contribution": money(300_000, "estimated"), "success_probability": scalar(0.5, "estimated")},
            {"id": "partner-webinar", "status": "proposed", "cash_cost": money(50_000), "effort_hours": scalar(5, "estimated"), "potential_gross_contribution": money(200_000, "estimated"), "success_probability": scalar(0.4, "estimated")},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["experiments"][0].update({"status": "completed", "required_sample_size": scalar(100), "available_sample_size": scalar(120), "observed_metric": scalar(0.08, "reported"), "success_threshold": scalar(0.07), "stop_threshold": scalar(0.03), "stop_loss": money(160_000)})
    data["experiments"][1].update({"status": "completed", "required_sample_size": scalar(100), "available_sample_size": scalar(100), "observed_metric": scalar(0.02, "reported"), "success_threshold": scalar(0.07), "stop_threshold": scalar(0.03), "stop_loss": money(80_000)})
    data["scenarios"] = [{"id": "downside", "probability_factor": scalar(0.5, "estimated"), "contribution_factor": scalar(0.8, "estimated"), "cash_cost_factor": scalar(1.2, "estimated")}]
    return data


def run_cli(data: object) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class GrowthExperimentTests(unittest.TestCase):
    def test_core_calculates_economics_and_keeps_order_separate(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("experiments", result)
        experiments = {item["id"]: item for item in result["experiments"]}
        self.assertEqual(experiments["pricing-page"]["internal_cost"], 50_000)
        self.assertEqual(experiments["pricing-page"]["expected_net_value"], 0)
        self.assertEqual(experiments["partner-webinar"]["expected_net_value"], 5_000)
        self.assertEqual(result["economic_order"], ["partner-webinar", "pricing-page"])
        self.assertEqual(result["analysis_quality"]["mode"], "core")

    def test_advanced_uses_sample_and_metric_gates_for_scale_and_stop(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("experiments", result)
        experiments = {item["id"]: item for item in result["experiments"]}
        self.assertEqual(experiments["pricing-page"]["decision_signal"], "scale")
        self.assertEqual(experiments["partner-webinar"]["decision_signal"], "stop")
        self.assertTrue(experiments["pricing-page"]["sample_sufficient"])

    def test_advanced_holds_when_sample_or_capacity_is_insufficient(self) -> None:
        data = advanced_payload()
        data["experiments"][0]["available_sample_size"] = scalar(20)
        data["experiments"][1]["status"] = "proposed"
        data["experiments"][1]["effort_hours"] = scalar(100)
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("experiments", result)
        experiments = {item["id"]: item for item in result["experiments"]}
        self.assertEqual(experiments["pricing-page"]["decision_signal"], "hold")
        self.assertIn("insufficient_sample", experiments["pricing-page"]["flags"])
        self.assertEqual(experiments["partner-webinar"]["decision_signal"], "hold")
        self.assertIn("capacity_exceeded", experiments["partner-webinar"]["flags"])

    def test_scenario_recalculates_without_changing_base_order(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("scenario_metrics", result)
        scenario = result["scenario_metrics"][0]
        self.assertEqual(scenario["id"], "downside")
        self.assertEqual(scenario["experiments"]["pricing-page"], -110_000)
        self.assertEqual(scenario["experiments"]["partner-webinar"], -53_000)
        self.assertEqual(result["economic_order"], ["partner-webinar", "pricing-page"])

    def test_unknown_probability_only_blocks_affected_experiment(self) -> None:
        data = payload()
        data["experiments"][0]["success_probability"] = scalar(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("experiments", result)
        self.assertEqual(result["experiments"][0]["status"], "indeterminate")
        self.assertEqual(result["economic_order"], ["partner-webinar"])
        self.assertIn("experiments[0].success_probability", result["analysis_quality"]["decision_changing_unknowns"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_rejects_contradictory_thresholds_duplicate_ids_and_bad_probability(self) -> None:
        data = advanced_payload()
        data["experiments"][0]["stop_threshold"] = scalar(0.08)
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["experiments"][1]["id"] = "pricing-page"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["experiments"][0]["success_probability"] = scalar(1.1)
        self.assertEqual(run_cli(data).returncode, 2)

    def test_rejects_unknown_encoded_as_zero_currency_mismatch_and_bad_mode(self) -> None:
        data = payload()
        data["experiments"][0]["effort_hours"] = scalar(0, "unknown")
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["experiments"][0]["cash_cost"]["currency"] = "USD"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["analysis_mode"] = "deep"
        self.assertEqual(run_cli(data).returncode, 2)

    def test_rejects_nonpositive_horizon_and_empty_experiments(self) -> None:
        data = payload()
        data["horizon_weeks"] = 0
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["experiments"] = []
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
