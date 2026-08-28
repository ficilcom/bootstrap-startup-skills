from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/operations/security-questionnaire-readiness/scripts/assess_security_readiness.py"
SPEC = importlib.util.spec_from_file_location("assess_security_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "reported") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def hours(value: float | None, evidence: str = "estimated") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def item(
    item_id: str,
    category: str,
    level: str,
    state: str,
    artifact: str,
    remediation: float | None,
    evidence: str = "estimated",
) -> dict[str, object]:
    return {
        "id": item_id,
        "category": category,
        "requirement_level": level,
        "current_state": state,
        "evidence_artifact": artifact,
        "remediation_hours": hours(remediation, evidence),
    }


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-28",
        "submission_deadline": "2026-10-09",
        "currency": "JPY",
        "available_hours_per_week": hours(6, "reported"),
        "items": [
            item("access-control-mfa", "access", "must", "implemented", "configuration", 0),
            item("access-control-review", "access", "must", "partial", "none", 8),
            item("endpoint-encryption", "endpoint", "must", "not_implemented", "none", 16),
            item("backup-restore-test", "backup", "should", "implemented", "log", 0),
            item("incident-response-plan", "incident", "should", "not_implemented", "none", 12),
            item("subcontractor-management", "subcontractor", "must", "implemented", "none", 4),
            item("security-training", "training", "optional", "not_implemented", "none", 5),
            item("log-retention", "logging", "should", "partial", "configuration", 6),
        ],
    }


def advanced() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    costs = {
        "access-control-review": 50_000,
        "endpoint-encryption": 200_000,
        "incident-response-plan": 0,
        "subcontractor-management": 30_000,
        "security-training": 20_000,
        "log-retention": 40_000,
    }
    for entry in data["items"]:
        if entry["id"] in costs:
            entry["remediation_cost"] = money(costs[entry["id"]])
    data["compensating_controls"] = [
        {
            "item_id": "endpoint-encryption",
            "description": "業務端末を貸与に限定し持出しを禁止する運用",
            "accepted_by_customer": True,
        }
    ]
    return data


class SecurityQuestionnaireReadinessTests(unittest.TestCase):
    def test_counts_only_implemented_items_with_evidence_as_answerable(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["totals"]["items"], 8)
        self.assertEqual(result["totals"]["answerable_now"], 2)
        self.assertEqual(result["totals"]["must_items"], 4)
        self.assertEqual(result["totals"]["must_answerable_now"], 1)
        self.assertEqual(
            [gap["id"] for gap in result["must_gaps"]],
            ["access-control-review", "endpoint-encryption", "subcontractor-management"],
        )
        self.assertEqual(
            result["readiness_scope"],
            "evidence-backed answerability and deadline arithmetic only; control effectiveness, certification, contractual acceptance, and customer judgement remain separate",
        )

    def test_category_coverage_uses_evidence_backed_answers(self) -> None:
        categories = {item["category"]: item for item in MODULE.calculate(payload())["category_coverage"]}

        self.assertEqual(categories["access"]["items"], 2)
        self.assertEqual(categories["access"]["answerable_now"], 1)
        self.assertEqual(categories["access"]["coverage_rate"], 0.5)
        self.assertEqual(categories["subcontractor"]["answerable_now"], 0)

    def test_back_schedules_remediation_against_the_deadline(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["schedule_summary"]["weeks_available"], 6)
        self.assertEqual(result["schedule_summary"]["remediation_hours_total"], 51)
        self.assertEqual(result["schedule_summary"]["required_weeks"], 8.5)
        self.assertFalse(result["schedule_summary"]["schedule_feasible"])
        self.assertEqual(result["schedule_summary"]["first_item_past_deadline"], "incident-response-plan")

        schedule = result["schedule"]
        self.assertEqual([entry["id"] for entry in schedule[:3]], ["subcontractor-management", "access-control-review", "endpoint-encryption"])
        self.assertEqual(schedule[0]["cumulative_weeks"], 0.666667)
        self.assertTrue(schedule[3]["fits_before_deadline"])
        self.assertFalse(schedule[4]["fits_before_deadline"])

    def test_unknown_hours_localize_without_becoming_zero(self) -> None:
        data = payload()
        data["items"][6]["remediation_hours"] = hours(None, "unknown")

        result = MODULE.calculate(data)
        schedule = {entry["id"]: entry for entry in result["schedule"]}

        self.assertIsNone(result["schedule_summary"]["remediation_hours_total"])
        self.assertEqual(result["schedule_summary"]["remediation_hours_known_floor"], 46)
        self.assertIsNone(result["schedule_summary"]["required_weeks"])
        self.assertIsNone(result["schedule_summary"]["schedule_feasible"])
        self.assertEqual(result["schedule_summary"]["first_item_past_deadline"], "incident-response-plan")
        self.assertIsNone(schedule["security-training"]["cumulative_weeks"])
        self.assertIsNone(schedule["security-training"]["fits_before_deadline"])
        self.assertIn("remediation_hours_incomplete", result["analysis_quality"]["warnings"])
        self.assertIn("items[6].remediation_hours", result["analysis_quality"]["decision_changing_unknowns"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_advanced_separates_accepted_compensating_controls_from_remaining_gaps(self) -> None:
        result = MODULE.calculate(advanced())

        self.assertEqual(result["must_gaps_covered_by_control"], ["endpoint-encryption"])
        self.assertEqual(result["must_gaps_remaining"], ["access-control-review", "subcontractor-management"])
        self.assertEqual(result["remediation_cost_total"], 340_000)

    def test_unaccepted_control_does_not_close_a_must_gap(self) -> None:
        data = advanced()
        data["compensating_controls"][0]["accepted_by_customer"] = None

        result = MODULE.calculate(data)

        self.assertEqual(result["must_gaps_covered_by_control"], [])
        self.assertIn("endpoint-encryption", result["must_gaps_remaining"])
        self.assertIn("compensating_controls[0].accepted_by_customer", result["analysis_quality"]["decision_changing_unknowns"])

    def test_core_mode_ignores_advanced_sections(self) -> None:
        data = advanced()
        data["analysis_mode"] = "core"

        result = MODULE.calculate(data)

        self.assertEqual(result["must_gaps_covered_by_control"], [])
        self.assertIsNone(result["remediation_cost_total"])

    def test_rejects_duplicate_ids_bad_dates_levels_and_unknown_references(self) -> None:
        data = payload()
        data["items"][1]["id"] = "access-control-mfa"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["submission_deadline"] = "2026-08-28"
        with self.assertRaisesRegex(ValueError, "submission_deadline"):
            MODULE.calculate(data)

        data = payload()
        data["items"][0]["requirement_level"] = "critical"
        with self.assertRaisesRegex(ValueError, "requirement_level"):
            MODULE.calculate(data)

        data = advanced()
        data["compensating_controls"][0]["item_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "known item"):
            MODULE.calculate(data)

    def test_rejects_empty_items_currency_mismatch_and_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["items"] = []
        with self.assertRaisesRegex(ValueError, "at least one"):
            MODULE.calculate(data)

        data = advanced()
        data["items"][1]["remediation_cost"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["available_hours_per_week"] = hours(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(advanced()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["totals"]["answerable_now"], 2)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
