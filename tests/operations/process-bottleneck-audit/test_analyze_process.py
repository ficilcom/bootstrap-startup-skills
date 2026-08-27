from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/operations/process-bottleneck-audit/scripts/analyze_process.py"
SPEC = importlib.util.spec_from_file_location("analyze_process", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "process_name": "customer-onboarding",
        "period_label": "2026-W34",
        "demand_units": scalar(100, "reported"),
        "steps": [
            {
                "name": "intake",
                "opening_wip_units": scalar(0),
                "arrived_units": scalar(100),
                "completed_units": scalar(90),
                "available_minutes": scalar(600),
                "work_minutes_per_unit": scalar(6, "reported"),
                "wait_time_hours": scalar(2, "reported"),
                "rework_units": scalar(0),
                "blocked_units": scalar(2),
            },
            {
                "name": "implementation",
                "opening_wip_units": scalar(10),
                "arrived_units": scalar(90),
                "completed_units": scalar(70),
                "available_minutes": scalar(600),
                "work_minutes_per_unit": scalar(8, "reported"),
                "wait_time_hours": scalar(10, "reported"),
                "rework_units": scalar(7),
                "blocked_units": scalar(12),
            },
            {
                "name": "quality-review",
                "opening_wip_units": scalar(0),
                "arrived_units": scalar(70),
                "completed_units": scalar(68),
                "available_minutes": scalar(600),
                "work_minutes_per_unit": scalar(5, "reported"),
                "wait_time_hours": scalar(5, "reported"),
                "rework_units": scalar(2),
                "blocked_units": scalar(0),
            },
        ],
    }


class AnalyzeProcessTests(unittest.TestCase):
    def test_calculates_capacity_flow_and_constraint_candidates(self) -> None:
        result = MODULE.calculate(payload())
        steps = {item["name"]: item for item in result["steps"]}

        implementation = steps["implementation"]
        self.assertEqual(implementation["capacity_units"], 75)
        self.assertEqual(implementation["capacity_shortfall_vs_demand"], 25)
        self.assertEqual(implementation["utilization"], 0.933333)
        self.assertEqual(implementation["closing_wip_units"], 30)
        self.assertEqual(implementation["backlog_periods_at_current_throughput"], 0.428571)
        self.assertEqual(implementation["first_pass_yield"], 0.9)
        self.assertEqual(result["final_throughput_units"], 68)
        self.assertEqual(result["demand_gap_units"], 32)
        self.assertEqual(result["constraint_candidates"][0], "implementation")

    def test_zero_throughput_leaves_backlog_duration_unknown(self) -> None:
        data = payload()
        data["steps"][1]["completed_units"] = scalar(0)
        data["steps"][1]["rework_units"] = scalar(0)

        result = MODULE.calculate(data)["steps"][1]

        self.assertIsNone(result["backlog_periods_at_current_throughput"])
        self.assertIn("zero_throughput", result["flags"])

    def test_unknown_core_input_makes_step_indeterminate_and_unranked(self) -> None:
        data = payload()
        data["steps"][1]["work_minutes_per_unit"] = scalar(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["steps"][1]["status"], "indeterminate")
        self.assertNotIn("implementation", result["constraint_candidates"])
        self.assertIn("steps[1].work_minutes_per_unit", result["missing_inputs"])

    def test_rejects_impossible_flow_rework_and_blocked_counts(self) -> None:
        data = payload()
        data["steps"][1]["completed_units"] = scalar(101)
        with self.assertRaisesRegex(ValueError, "available units"):
            MODULE.calculate(data)

        data = payload()
        data["steps"][1]["rework_units"] = scalar(71)
        with self.assertRaisesRegex(ValueError, "rework_units"):
            MODULE.calculate(data)

        data = payload()
        data["steps"][1]["blocked_units"] = scalar(31)
        with self.assertRaisesRegex(ValueError, "blocked_units"):
            MODULE.calculate(data)

    def test_rejects_duplicate_steps_and_nonpositive_work_time(self) -> None:
        data = payload()
        data["steps"][1]["name"] = "intake"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["steps"][0]["work_minutes_per_unit"] = scalar(0)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["demand_units"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_candidate_order_is_descriptive_not_a_health_threshold(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["candidate_order_scope"], "known capacity shortfall, closing WIP, wait, then utilization")
        self.assertEqual(result["constraint_candidates"], ["implementation", "intake", "quality-review"])

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["final_throughput_units"], 68)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
