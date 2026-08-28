from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/operations/vendor-selection-review/scripts/compare_vendors.py"
SPEC = importlib.util.spec_from_file_location("compare_vendors", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: int | float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "horizon_months": 12,
        "internal_hourly_cost": money(5_000),
        "options": [
            {"name": "vendor-a", "initial_cost": money(100_000), "monthly_cost": money(30_000), "monthly_usage_cost": money(10_000), "migration_hours": scalar(20), "exit_cost": money(50_000), "contract_months": 12, "lock_in_score": 4, "fit_score": 5, "reliability_score": 4},
            {"name": "vendor-b", "initial_cost": money(50_000), "monthly_cost": money(35_000), "monthly_usage_cost": money(5_000), "migration_hours": scalar(10), "exit_cost": money(10_000), "contract_months": 1, "lock_in_score": 1, "fit_score": 4, "reliability_score": 3},
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["requirements"] = [
        {"id": "data-export", "importance": "must"},
        {"id": "sla", "importance": "should"},
    ]
    data["options"][0].update({
        "implementation_external_cost": money(20_000),
        "training_hours": scalar(10),
        "monthly_support_cost": money(5_000),
        "renewal_monthly_cost": money(40_000),
        "renewal_start_month": 7,
        "data_export_cost": money(20_000),
        "requirement_results": [
            {"id": "data-export", "status": "failed"},
            {"id": "sla", "status": "verified"},
        ],
    })
    data["options"][1].update({
        "implementation_external_cost": money(0),
        "training_hours": scalar(0),
        "monthly_support_cost": money(0),
        "renewal_monthly_cost": money(35_000),
        "renewal_start_month": 1,
        "data_export_cost": money(0),
        "requirement_results": [
            {"id": "data-export", "status": "verified"},
            {"id": "sla", "status": "unknown"},
        ],
    })
    data["scenarios"] = [{
        "name": "high-usage",
        "option_overrides": [
            {"name": "vendor-a", "monthly_usage_cost": money(25_000)},
            {"name": "vendor-b", "monthly_usage_cost": money(30_000)},
        ],
    }]
    return data


class VendorSelectionTests(unittest.TestCase):
    def test_core_mode_adds_quality_without_changing_tco(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["analysis_quality"]["mode"], "core")
        self.assertEqual(result["analysis_quality"]["status"], "complete")
        self.assertEqual(result["options"][0]["horizon_tco"], 730_000)
        self.assertEqual(result["cost_order"], ["vendor-b", "vendor-a"])

    def test_advanced_mode_adds_lifecycle_costs_and_requirement_gates(self) -> None:
        result = MODULE.calculate(advanced_payload())
        options = {item["name"]: item for item in result["options"]}

        self.assertEqual(options["vendor-a"]["advanced_horizon_tco"], 940_000)
        self.assertEqual(options["vendor-a"]["eligibility_status"], "disqualified")
        self.assertEqual(options["vendor-a"]["failed_gates"], ["data-export"])
        self.assertEqual(options["vendor-b"]["eligibility_status"], "conditional")
        self.assertEqual(options["vendor-b"]["unverified_gates"], ["sla"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_advanced_scenario_recalculates_each_option_without_changing_base_order(self) -> None:
        result = MODULE.calculate(advanced_payload())
        scenario = result["scenario_tco"][0]

        self.assertEqual(scenario["name"], "high-usage")
        self.assertEqual(scenario["options"]["vendor-a"], 1_120_000)
        self.assertEqual(scenario["options"]["vendor-b"], 890_000)
        self.assertEqual(result["cost_order"], ["vendor-b", "vendor-a"])

    def test_advanced_scenario_accepts_zero_cost_override(self) -> None:
        data = advanced_payload()
        data["scenarios"][0]["option_overrides"][0]["monthly_usage_cost"] = money(0)

        scenario = MODULE.calculate(data)["scenario_tco"][0]

        self.assertEqual(scenario["options"]["vendor-a"], 820_000)

    def test_advanced_mode_rejects_unknown_requirements_bad_terms_and_scenario_options(self) -> None:
        data = advanced_payload()
        data["requirements"][1]["id"] = "data-export"
        with self.assertRaisesRegex(ValueError, "requirement ids must be unique"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["options"][0]["requirement_results"][0]["id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown requirement"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["options"][0]["renewal_start_month"] = 13
        with self.assertRaisesRegex(ValueError, "renewal_start_month"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["scenarios"][0]["option_overrides"][0]["name"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown option"):
            MODULE.calculate(data)

    def test_calculates_tco_and_cost_order(self) -> None:
        result = MODULE.calculate(payload())
        options = {item["name"]: item for item in result["options"]}

        self.assertEqual(options["vendor-a"]["migration_internal_cost"], 100_000)
        self.assertEqual(options["vendor-a"]["horizon_tco"], 730_000)
        self.assertEqual(options["vendor-a"]["average_monthly_cost"], 60_833.333333)
        self.assertEqual(options["vendor-b"]["horizon_tco"], 590_000)
        self.assertEqual(result["cost_order"], ["vendor-b", "vendor-a"])

    def test_contract_and_lock_in_are_flags_not_hidden_in_cost(self) -> None:
        option = MODULE.calculate(payload())["options"][0]

        self.assertIn("high_lock_in", option["flags"])
        self.assertIn("long_commitment", option["flags"])
        self.assertEqual(option["fit_score"], 5)

    def test_zero_horizon_is_rejected_instead_of_dividing(self) -> None:
        data = payload()
        data["horizon_months"] = 0

        with self.assertRaisesRegex(ValueError, "positive integer"):
            MODULE.calculate(data)

    def test_unknown_cost_keeps_option_indeterminate_and_unranked(self) -> None:
        data = payload()
        data["options"][0]["monthly_usage_cost"] = money(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["options"][0]["status"], "indeterminate")
        self.assertNotIn("vendor-a", result["cost_order"])
        self.assertIn("options[0].monthly_usage_cost", result["missing_inputs"])

    def test_zero_migration_hours_are_valid(self) -> None:
        data = payload()
        data["options"][0]["migration_hours"] = scalar(0)

        option = MODULE.calculate(data)["options"][0]

        self.assertEqual(option["migration_internal_cost"], 0)
        self.assertEqual(option["horizon_tco"], 630_000)

    def test_rejects_duplicate_options_bad_scores_and_currency(self) -> None:
        data = payload()
        data["options"][1]["name"] = "vendor-a"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["options"][0]["lock_in_score"] = 6
        with self.assertRaisesRegex(ValueError, "between 0 and 5"):
            MODULE.calculate(data)

        data = payload()
        data["options"][0]["initial_cost"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero_and_invalid_contract_term(self) -> None:
        data = payload()
        data["options"][0]["migration_hours"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["options"][0]["contract_months"] = -1
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["cost_order"][0], "vendor-b")

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
