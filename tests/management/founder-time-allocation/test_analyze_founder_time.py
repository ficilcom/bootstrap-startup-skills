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


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["observed_weeks"] = 2
    data["planning_horizon_weeks"] = 8
    data["fragmentation_threshold_per_week"] = scalar(4)
    transfers = {
        "customer-discovery": {"frequency_per_week": scalar(3), "context_switches": scalar(10), "outcome_metric": "validated interviews", "transfer": {"transferable_rate": scalar(0), "initial_transition_hours": scalar(0), "weekly_oversight_hours": scalar(0), "recipient_capacity_hours": scalar(0), "procedure_status": "ready", "quality_status": "ready", "authority_status": "ready"}},
        "invoice-entry": {"frequency_per_week": scalar(4), "context_switches": scalar(4), "outcome_metric": "entries completed accurately", "transfer": {"transferable_rate": scalar(1), "initial_transition_hours": scalar(6), "weekly_oversight_hours": scalar(0.5), "recipient_capacity_hours": scalar(5), "procedure_status": "ready", "quality_status": "ready", "authority_status": "ready"}},
        "status-meetings": {"frequency_per_week": scalar(3), "context_switches": scalar(6), "outcome_metric": "decisions unblocked", "transfer": {"transferable_rate": scalar(1), "initial_transition_hours": scalar(20), "weekly_oversight_hours": scalar(1), "recipient_capacity_hours": scalar(3), "procedure_status": "ready", "quality_status": "ready", "authority_status": "ready"}},
    }
    for activity in data["activities"]:
        activity.update(transfers[activity["name"]])
    return data


class FounderTimeTests(unittest.TestCase):
    def test_core_mode_adds_quality_without_changing_candidates(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["analysis_quality"]["mode"], "core")
        self.assertEqual(result["analysis_quality"]["status"], "complete")
        self.assertEqual(result["summary"]["reclaimable_hours"], 14)
        self.assertEqual(result["delegate_candidates"], ["invoice-entry"])

    def test_advanced_mode_calculates_transition_economics(self) -> None:
        result = MODULE.calculate(advanced_payload())
        activities = {item["name"]: item for item in result["activities"]}
        invoice = activities["invoice-entry"]["transition_economics"]

        self.assertEqual(activities["invoice-entry"]["weekly_hours"], 4)
        self.assertEqual(invoice["gross_reclaimable_hours"], 32)
        self.assertEqual(invoice["net_reclaimable_hours"], 22)
        self.assertEqual(invoice["payback_weeks"], 1.714286)
        self.assertEqual(invoice["status"], "viable")

    def test_advanced_mode_blocks_or_rejects_unsafe_and_uneconomic_transitions(self) -> None:
        result = MODULE.calculate(advanced_payload())
        activities = {item["name"]: item for item in result["activities"]}

        self.assertEqual(activities["customer-discovery"]["transition_economics"]["status"], "blocked")
        self.assertIn("founder_required", activities["customer-discovery"]["transition_gates"])
        self.assertEqual(activities["status-meetings"]["transition_economics"]["net_reclaimable_hours"], -4)
        self.assertEqual(activities["status-meetings"]["transition_economics"]["status"], "uneconomic")

    def test_advanced_mode_protects_fragmented_high_value_work(self) -> None:
        activity = {item["name"]: item for item in MODULE.calculate(advanced_payload())["activities"]}["customer-discovery"]

        self.assertEqual(activity["context_switches_per_week"], 5)
        self.assertIn("focus_fragmentation", activity["flags"])
        self.assertIn("customer-discovery", MODULE.calculate(advanced_payload())["protect_candidates"])

    def test_advanced_mode_rejects_bad_horizons_rates_and_readiness(self) -> None:
        data = advanced_payload()
        data["observed_weeks"] = 0
        with self.assertRaisesRegex(ValueError, "observed_weeks"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["activities"][1]["transfer"]["transferable_rate"] = scalar(1.1)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["activities"][1]["transfer"]["procedure_status"] = "done"
        with self.assertRaisesRegex(ValueError, "procedure_status"):
            MODULE.calculate(data)

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
