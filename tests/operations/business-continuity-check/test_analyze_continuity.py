from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/operations/business-continuity-check/scripts/analyze_continuity.py"
SPEC = importlib.util.spec_from_file_location("analyze_continuity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "review_date": "2026-08-22",
        "dependencies": [
            {"name": "cloud-platform", "type": "system", "criticality": 5, "outage_probability": scalar(0.1, "estimated"), "maximum_tolerable_downtime_hours": scalar(4), "expected_recovery_hours": scalar(8, "reported"), "tested_alternative": False, "owner": "ops", "depends_on": []},
            {"name": "billing", "type": "process", "criticality": 4, "outage_probability": scalar(0.05, "estimated"), "maximum_tolerable_downtime_hours": scalar(24), "expected_recovery_hours": scalar(8), "tested_alternative": True, "owner": "finance", "depends_on": ["cloud-platform"]},
            {"name": "customer-portal", "type": "system", "criticality": 4, "outage_probability": scalar(0.08, "estimated"), "maximum_tolerable_downtime_hours": scalar(8), "expected_recovery_hours": scalar(4), "tested_alternative": False, "owner": "product", "depends_on": ["cloud-platform"]},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["dependencies"][0].update({
        "tested_alternative": True,
        "recovery_point_objective_hours": scalar(2),
        "expected_data_loss_hours": scalar(6, "reported"),
        "minimum_operating_capacity_rate": scalar(0.8),
        "alternative_capacity_rate": scalar(0.5, "reported"),
        "alternative_recovery_hours": scalar(10, "reported"),
        "last_test_date": "2026-07-15",
        "test_result": "failed",
    })
    data["dependencies"][1].update({
        "recovery_point_objective_hours": scalar(None, "unknown"),
        "expected_data_loss_hours": scalar(None, "unknown"),
        "minimum_operating_capacity_rate": scalar(0.5),
        "alternative_capacity_rate": scalar(1),
        "alternative_recovery_hours": scalar(6),
        "last_test_date": "2026-08-01",
        "test_result": "passed",
    })
    data["dependencies"][2].update({
        "recovery_point_objective_hours": scalar(1),
        "expected_data_loss_hours": scalar(1),
        "minimum_operating_capacity_rate": scalar(0.5),
        "alternative_capacity_rate": scalar(0.5),
        "alternative_recovery_hours": scalar(4),
        "last_test_date": None,
        "test_result": "not_run",
    })
    data["scenarios"] = [
        {"name": "platform-and-owner-loss", "failed_dependencies": ["cloud-platform", "billing"]}
    ]
    return data


class ContinuityTests(unittest.TestCase):
    def test_core_mode_adds_quality_without_changing_existing_results(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["analysis_quality"]["mode"], "core")
        self.assertEqual(result["analysis_quality"]["status"], "complete")
        self.assertEqual(result["risk_order"][0], "cloud-platform")
        self.assertEqual(result["dependencies"][0]["risk_score"], 3)

    def test_advanced_mode_exposes_recovery_gaps_layers_and_priority(self) -> None:
        result = MODULE.calculate(advanced_payload())
        dependencies = {item["name"]: item for item in result["dependencies"]}

        self.assertEqual(dependencies["cloud-platform"]["rpo_gap_hours"], 4)
        self.assertEqual(dependencies["cloud-platform"]["alternative_capacity_gap_rate"], 0.3)
        self.assertEqual(dependencies["cloud-platform"]["priority_tier"], "critical")
        self.assertEqual(result["recovery_layers"], [["cloud-platform"], ["billing", "customer-portal"]])
        self.assertEqual(result["analysis_quality"]["status"], "partial")
        self.assertIn("dependencies[1].recovery_point_objective_hours", result["analysis_quality"]["decision_changing_unknowns"])

    def test_advanced_scenarios_union_direct_and_transitive_impact(self) -> None:
        scenario = MODULE.calculate(advanced_payload())["scenario_impacts"][0]

        self.assertEqual(scenario["name"], "platform-and-owner-loss")
        self.assertEqual(scenario["failed_dependencies"], ["billing", "cloud-platform"])
        self.assertEqual(scenario["affected_dependencies"], ["billing", "cloud-platform", "customer-portal"])

    def test_advanced_mode_rejects_invalid_modes_dates_results_and_scenario_references(self) -> None:
        data = payload()
        data["analysis_mode"] = "deep"
        with self.assertRaisesRegex(ValueError, "analysis_mode"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["dependencies"][0]["last_test_date"] = "15-07-2026"
        with self.assertRaisesRegex(ValueError, "ISO date"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["dependencies"][0]["test_result"] = "passed"
        data["dependencies"][0]["tested_alternative"] = False
        with self.assertRaisesRegex(ValueError, "contradicts tested_alternative"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["scenarios"][0]["failed_dependencies"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            MODULE.calculate(data)

    def test_calculates_recovery_gap_blast_radius_and_risk_order(self) -> None:
        result = MODULE.calculate(payload())
        dependencies = {item["name"]: item for item in result["dependencies"]}

        self.assertEqual(dependencies["cloud-platform"]["recovery_gap_hours"], 4)
        self.assertEqual(dependencies["cloud-platform"]["affected_dependencies"], ["billing", "customer-portal"])
        self.assertEqual(dependencies["cloud-platform"]["blast_radius_count"], 2)
        self.assertEqual(dependencies["cloud-platform"]["risk_score"], 3)
        self.assertEqual(result["risk_order"][0], "cloud-platform")

    def test_flags_single_points_and_recovery_breaches(self) -> None:
        dependency = MODULE.calculate(payload())["dependencies"][0]

        self.assertIn("no_tested_alternative", dependency["flags"])
        self.assertIn("recovery_exceeds_tolerance", dependency["flags"])

    def test_missing_owner_is_flagged_without_fabricating_one(self) -> None:
        data = payload()
        data["dependencies"][1]["owner"] = None

        dependency = MODULE.calculate(data)["dependencies"][1]

        self.assertIn("missing_owner", dependency["flags"])
        self.assertIsNone(dependency["owner"])

    def test_unknown_recovery_keeps_dependency_unranked(self) -> None:
        data = payload()
        data["dependencies"][0]["expected_recovery_hours"] = scalar(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["dependencies"][0]["status"], "indeterminate")
        self.assertNotIn("cloud-platform", result["risk_order"])
        self.assertIn("dependencies[0].expected_recovery_hours", result["missing_inputs"])

    def test_transitive_blast_radius_is_included(self) -> None:
        data = payload()
        data["dependencies"].append({"name": "collections", "type": "process", "criticality": 2, "outage_probability": scalar(0.02), "maximum_tolerable_downtime_hours": scalar(48), "expected_recovery_hours": scalar(4), "tested_alternative": True, "owner": "finance", "depends_on": ["billing"]})

        dependency = {item["name"]: item for item in MODULE.calculate(data)["dependencies"]}["cloud-platform"]

        self.assertEqual(dependency["affected_dependencies"], ["billing", "collections", "customer-portal"])

    def test_rejects_unknown_references_cycles_and_bad_probability(self) -> None:
        data = payload()
        data["dependencies"][1]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            MODULE.calculate(data)

        data = payload()
        data["dependencies"][0]["depends_on"] = ["billing"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            MODULE.calculate(data)

        data = payload()
        data["dependencies"][0]["outage_probability"] = scalar(1.1)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            MODULE.calculate(data)

    def test_rejects_duplicate_names_unknown_encoded_as_zero_and_bad_boolean(self) -> None:
        data = payload()
        data["dependencies"][1]["name"] = "cloud-platform"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["dependencies"][0]["expected_recovery_hours"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["dependencies"][0]["tested_alternative"] = "no"
        with self.assertRaisesRegex(ValueError, "boolean"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["risk_order"][0], "cloud-platform")

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
