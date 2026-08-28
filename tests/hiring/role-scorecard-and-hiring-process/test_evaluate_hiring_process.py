from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/hiring/role-scorecard-and-hiring-process/scripts/evaluate_hiring_process.py"


def rating(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "role_id": "first-ae",
        "criteria": [
            {"id": "pipeline", "kind": "outcome", "weight": 50, "minimum_rating": 3},
            {"id": "discovery", "kind": "competency", "weight": 30, "minimum_rating": 3},
            {"id": "startup-selling", "kind": "must", "weight": 20, "minimum_rating": 3},
        ],
        "candidates": [
            {"id": "candidate-a", "evaluations": [{"id": "pipeline", "rating": rating(5, "reported")}, {"id": "discovery", "rating": rating(4, "reported")}, {"id": "startup-selling", "rating": rating(4, "confirmed")}]},
            {"id": "candidate-b", "evaluations": [{"id": "pipeline", "rating": rating(5, "reported")}, {"id": "discovery", "rating": rating(5, "reported")}, {"id": "startup-selling", "rating": rating(2, "confirmed")}]},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["process_checks"] = [{"id": "work-sample", "required": True}, {"id": "references", "required": False}]
    data["candidates"][0]["process_results"] = [{"id": "work-sample", "status": "unknown"}, {"id": "references", "status": "reported"}]
    data["candidates"][1]["process_results"] = [{"id": "work-sample", "status": "failed"}, {"id": "references", "status": "unknown"}]
    data["scenarios"] = [{"id": "outcome-heavy", "weight_overrides": [{"id": "pipeline", "weight": 80}, {"id": "discovery", "weight": 10}, {"id": "startup-selling", "weight": 10}]}]
    return data


def run_cli(data: object) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)


class HiringProcessTests(unittest.TestCase):
    def test_scores_candidates_but_does_not_rescue_failed_must_gate(self) -> None:
        completed = run_cli(payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("candidates", result)
        candidates = {item["id"]: item for item in result["candidates"]}
        self.assertEqual(candidates["candidate-a"]["weighted_score"], 4.5)
        self.assertEqual(candidates["candidate-a"]["eligibility_status"], "eligible")
        self.assertEqual(candidates["candidate-a"]["decision_signal"], "advance")
        self.assertEqual(candidates["candidate-b"]["weighted_score"], 4.4)
        self.assertEqual(candidates["candidate-b"]["eligibility_status"], "disqualified")
        self.assertEqual(candidates["candidate-b"]["decision_signal"], "do_not_advance")
        self.assertEqual(result["evidence_order"], ["candidate-a", "candidate-b"])

    def test_unknown_rating_only_blocks_affected_score(self) -> None:
        data = payload()
        data["candidates"][0]["evaluations"][0]["rating"] = rating(None, "unknown")
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("candidates", result)
        self.assertIsNone(result["candidates"][0]["weighted_score"])
        self.assertEqual(result["candidates"][0]["decision_signal"], "hold")
        self.assertEqual(result["evidence_order"], ["candidate-b"])
        self.assertIn("candidates[0].criteria.pipeline", result["analysis_quality"]["decision_changing_unknowns"])

    def test_advanced_required_process_checks_are_hard_gates(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("candidates", result)
        candidates = {item["id"]: item for item in result["candidates"]}
        self.assertEqual(candidates["candidate-a"]["eligibility_status"], "conditional")
        self.assertIn("work-sample", candidates["candidate-a"]["unknown_gates"])
        self.assertEqual(candidates["candidate-b"]["eligibility_status"], "disqualified")
        self.assertIn("work-sample", candidates["candidate-b"]["failed_gates"])

    def test_weight_scenario_reports_sensitivity_without_changing_base_order(self) -> None:
        completed = run_cli(advanced_payload())
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("scenario_scores", result)
        scenario = result["scenario_scores"][0]
        self.assertEqual(scenario["id"], "outcome-heavy")
        self.assertEqual(scenario["candidates"]["candidate-a"], 4.8)
        self.assertEqual(scenario["candidates"]["candidate-b"], 4.7)
        self.assertEqual(result["evidence_order"], ["candidate-a", "candidate-b"])

    def test_missing_must_evaluation_is_conditional_not_zero(self) -> None:
        data = payload()
        data["candidates"][0]["evaluations"] = data["candidates"][0]["evaluations"][:2]
        completed = run_cli(data)
        self.assertEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertIn("candidates", result)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["eligibility_status"], "conditional")
        self.assertIn("startup-selling", candidate["unknown_gates"])
        self.assertIsNone(candidate["weighted_score"])

    def test_rejects_duplicate_ids_bad_references_and_duplicate_evaluations(self) -> None:
        data = payload()
        data["criteria"][1]["id"] = "pipeline"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["candidates"][0]["evaluations"][0]["id"] = "missing"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["candidates"][0]["evaluations"][1]["id"] = "pipeline"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["candidates"][1]["id"] = "candidate-a"
        self.assertEqual(run_cli(data).returncode, 2)

    def test_rejects_bad_weights_ratings_process_status_unknown_zero_and_mode(self) -> None:
        data = payload()
        data["criteria"][0]["weight"] = 0
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["candidates"][0]["evaluations"][0]["rating"] = rating(6)
        self.assertEqual(run_cli(data).returncode, 2)
        data = advanced_payload()
        data["candidates"][0]["process_results"][0]["status"] = "maybe"
        self.assertEqual(run_cli(data).returncode, 2)
        data = payload()
        data["candidates"][0]["evaluations"][0]["rating"] = rating(0, "unknown")
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
