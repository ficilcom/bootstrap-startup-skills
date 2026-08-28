from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/hiring/contractor-or-employment-structuring/scripts/assess_engagement_structure.py"
SPEC = importlib.util.spec_from_file_location("assess_engagement_structure", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "reported") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def rate(value: float | None, evidence: str = "estimated") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def factor(factor_id: str, name: str, observation: str, evidence: str) -> dict[str, object]:
    return {"id": factor_id, "factor": name, "observation": observation, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "currency": "JPY",
        "engagement": {
            "monthly_fee": money(500_000, "confirmed"),
            "months_engaged": 18,
            "expected_months_remaining": 12,
        },
        "factors": [
            factor("f-direction", "direction_and_control", "employment_like", "reported"),
            factor("f-discretion", "work_discretion", "mixed", "reported"),
            factor("f-time-place", "time_and_place_constraint", "employment_like", "confirmed"),
            factor("f-remuneration", "remuneration_character", "employment_like", "reported"),
            factor("f-exclusivity", "exclusivity", "independent", "confirmed"),
            factor("f-substitutability", "substitutability", "unknown", "unknown"),
            factor("f-equipment", "equipment_burden", "independent", "reported"),
        ],
    }


def advanced() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["reclassification_cost_assumptions"] = {
        "base": {
            "employer_burden_rate": rate(0.16),
            "retroactive_months": 24,
            "estimated_unpaid_overtime": money(600_000, "estimated"),
            "other_costs": [{"name": "手続と専門家費用", "amount": money(200_000, "estimated")}],
        },
        "downside": {
            "employer_burden_rate": rate(0.16),
            "retroactive_months": 36,
            "estimated_unpaid_overtime": money(1_500_000, "estimated"),
            "other_costs": [{"name": "手続と専門家費用", "amount": money(400_000, "estimated")}],
        },
    }
    data["mitigations"] = [
        {
            "id": "m-place",
            "factor_ids": ["f-time-place"],
            "change": "作業場所と時間の指定をやめ、成果物と納期の合意に切り替える",
            "feasibility": "high",
            "cost": money(0, "confirmed"),
            "business_impact": "常時対応を前提とした運用ができなくなる",
        },
        {
            "id": "m-scope",
            "factor_ids": ["f-direction", "f-remuneration"],
            "change": "作業指示を業務範囲の合意へ置き換え、報酬を時間単価から成果物単位へ変更する",
            "feasibility": "low",
            "cost": money(300_000, "estimated"),
            "business_impact": "見積と検収の運用を新たに作る必要がある",
        },
    ]
    return data


class EngagementStructureTests(unittest.TestCase):
    def test_tallies_observations_and_preserves_evidence_per_factor(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(
            result["observation_counts"],
            {"employment_like": 3, "independent": 2, "mixed": 1, "unknown": 1},
        )
        self.assertEqual(
            [entry["id"] for entry in result["employment_like_factors"]],
            ["f-direction", "f-remuneration", "f-time-place"],
        )
        self.assertEqual(result["employment_like_factors"][2]["evidence"], "confirmed")
        self.assertEqual(result["unknown_factors"], ["f-substitutability"])
        self.assertEqual(result["factors_not_supplied"], [])
        self.assertEqual(result["risk_signal_count"], 3)
        self.assertEqual(
            result["classification_scope"],
            "observation tally and user-supplied cost arithmetic only; classification, administrative or judicial determination, insurance and tax liability, and remedy remain separate",
        )

    def test_reports_engagement_economics_and_missing_factors(self) -> None:
        data = payload()
        data["factors"] = data["factors"][:3]

        result = MODULE.calculate(data)

        self.assertEqual(result["engagement_economics"]["fee_to_date"], 9_000_000)
        self.assertEqual(result["engagement_economics"]["remaining_fee"], 6_000_000)
        self.assertEqual(
            result["factors_not_supplied"],
            ["equipment_burden", "exclusivity", "remuneration_character", "substitutability"],
        )

    def test_advanced_costs_use_only_user_supplied_assumptions(self) -> None:
        result = MODULE.calculate(advanced())

        self.assertEqual(result["reclassification_cost"]["base"], 2_720_000)
        self.assertEqual(result["reclassification_cost"]["downside"], 4_780_000)
        self.assertEqual(result["reclassification_cost"]["base_to_remaining_fee_ratio"], 0.453333)
        self.assertEqual(result["reclassification_cost"]["downside_to_remaining_fee_ratio"], 0.796667)

    def test_mitigations_report_covered_and_uncovered_factors(self) -> None:
        result = MODULE.calculate(advanced())
        mitigations = {entry["id"]: entry for entry in result["mitigations"]}

        self.assertEqual(mitigations["m-place"]["covered_employment_like_factors"], ["f-time-place"])
        self.assertEqual(mitigations["m-scope"]["covered_employment_like_factors"], ["f-direction", "f-remuneration"])
        self.assertEqual(mitigations["m-scope"]["feasibility"], "low")
        self.assertEqual(result["employment_like_factors_uncovered"], [])

        data = advanced()
        data["mitigations"] = data["mitigations"][:1]
        self.assertEqual(
            MODULE.calculate(data)["employment_like_factors_uncovered"],
            ["f-direction", "f-remuneration"],
        )

    def test_unknown_assumption_localizes_to_its_own_scenario(self) -> None:
        data = advanced()
        data["reclassification_cost_assumptions"]["base"]["employer_burden_rate"] = rate(None, "unknown")

        result = MODULE.calculate(data)

        self.assertIsNone(result["reclassification_cost"]["base"])
        self.assertIsNone(result["reclassification_cost"]["base_to_remaining_fee_ratio"])
        self.assertEqual(result["reclassification_cost"]["downside"], 4_780_000)
        self.assertIn(
            "reclassification_cost_assumptions.base.employer_burden_rate",
            result["analysis_quality"]["decision_changing_unknowns"],
        )
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_unobserved_factor_is_recorded_as_decision_changing(self) -> None:
        result = MODULE.calculate(payload())

        self.assertIn("factors[5].observation", result["analysis_quality"]["decision_changing_unknowns"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_core_mode_ignores_advanced_sections(self) -> None:
        data = advanced()
        data["analysis_mode"] = "core"

        result = MODULE.calculate(data)

        self.assertEqual(result["reclassification_cost"], {})
        self.assertEqual(result["mitigations"], [])

    def test_rejects_duplicate_ids_repeated_factors_and_inconsistent_evidence(self) -> None:
        data = payload()
        data["factors"][1]["id"] = "f-direction"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["factors"][1]["factor"] = "direction_and_control"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["factors"][5]["evidence"] = "reported"
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["factors"][0]["factor"] = "attitude"
        with self.assertRaisesRegex(ValueError, "factor"):
            MODULE.calculate(data)

    def test_rejects_unknown_mitigation_reference_currency_and_unknown_encoded_as_zero(self) -> None:
        data = advanced()
        data["mitigations"][0]["factor_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "known factor"):
            MODULE.calculate(data)

        data = payload()
        data["engagement"]["monthly_fee"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["engagement"]["monthly_fee"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(advanced()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["risk_signal_count"], 3)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
