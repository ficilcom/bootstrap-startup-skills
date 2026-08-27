from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/management/founder-time-allocation/scripts/analyze_founder_time.py"
SPEC = importlib.util.spec_from_file_location("analyze_founder_time", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "review_period": "typical-week",
        "available_hours": scalar(40),
        "activities": [
            {"name": "customer-discovery", "category": "growth", "hours": scalar(12), "founder_required": True, "value_score": 5, "leverage_score": 5, "delegation_readiness": 1},
            {"name": "invoice-entry", "category": "admin", "hours": scalar(8), "founder_required": False, "value_score": 2, "leverage_score": 1, "delegation_readiness": 5},
            {"name": "status-meetings", "category": "coordination", "hours": scalar(6), "founder_required": False, "value_score": 1, "leverage_score": 1, "delegation_readiness": 2},
        ],
    }


class FounderTimeTests(unittest.TestCase):
    def test_calculates_time_shares_focus_and_remaining_capacity(self) -> None:
        result = MODULE.calculate(payload())
        activities = {item["name"]: item for item in result["activities"]}

        self.assertEqual(result["summary"]["allocated_hours"], 26)
        self.assertEqual(result["summary"]["unallocated_hours"], 14)
        self.assertEqual(activities["customer-discovery"]["time_share"], 0.3)
        self.assertEqual(activities["customer-discovery"]["focus_score"], 25)

    def test_classifies_protect_delegate_and_eliminate_candidates(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["protect_candidates"], ["customer-discovery"])
        self.assertEqual(result["delegate_candidates"], ["invoice-entry"])
        self.assertEqual(result["eliminate_or_reduce_candidates"], ["status-meetings"])
        self.assertEqual(result["summary"]["reclaimable_hours"], 14)

    def test_overallocation_is_flagged_and_not_hidden(self) -> None:
        data = payload()
        data["available_hours"] = scalar(20)

        summary = MODULE.calculate(data)["summary"]

        self.assertEqual(summary["overallocated_hours"], 6)
        self.assertEqual(summary["unallocated_hours"], 0)

    def test_unknown_hours_make_totals_indeterminate_but_keep_known_candidates(self) -> None:
        data = payload()
        data["activities"][1]["hours"] = scalar(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["summary"]["status"], "indeterminate")
        self.assertIsNone(result["summary"]["allocated_hours"])
        self.assertIn("customer-discovery", result["protect_candidates"])
        self.assertIn("activities[1].hours", result["missing_inputs"])

    def test_required_founder_work_is_not_auto_delegated(self) -> None:
        data = payload()
        data["activities"][0]["delegation_readiness"] = 5

        result = MODULE.calculate(data)

        self.assertNotIn("customer-discovery", result["delegate_candidates"])
        self.assertIn("customer-discovery", result["protect_candidates"])

    def test_rejects_duplicate_activities_bad_scores_and_boolean_shape(self) -> None:
        data = payload()
        data["activities"][1]["name"] = "customer-discovery"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["activities"][0]["value_score"] = 6
        with self.assertRaisesRegex(ValueError, "between 0 and 5"):
            MODULE.calculate(data)

        data = payload()
        data["activities"][0]["founder_required"] = "yes"
        with self.assertRaisesRegex(ValueError, "boolean"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero_and_zero_available_hours(self) -> None:
        data = payload()
        data["activities"][0]["hours"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["available_hours"] = scalar(0)
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["summary"]["reclaimable_hours"], 14)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
