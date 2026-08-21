from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/finance/bank-loan-readiness/scripts/calculate_score.py"
SPEC = importlib.util.spec_from_file_location("calculate_score", SCRIPT)
assert SPEC and SPEC.loader
score_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score_module)


def startup_payload(rating: int = 5, evidence: str = "confirmed") -> dict[str, object]:
    return {
        "mode": "startup",
        "criteria": {
            "business_plan": {"rating": rating, "evidence": evidence},
            "funding_plan": {"rating": rating, "evidence": evidence},
            "repayment_capacity": {"rating": rating, "evidence": evidence},
            "founder_capability": {"rating": rating, "evidence": evidence},
            "compliance": {"rating": rating, "evidence": evidence},
            "documentation": {"rating": rating, "evidence": evidence},
        },
        "red_flags": [],
    }


def operating_company_payload(
    rating: int = 5, evidence: str = "confirmed"
) -> dict[str, object]:
    return {
        "mode": "operating_company",
        "criteria": {
            "repayment_capacity": {"rating": rating, "evidence": evidence},
            "financial_health": {"rating": rating, "evidence": evidence},
            "business_viability": {"rating": rating, "evidence": evidence},
            "borrowing_suitability": {"rating": rating, "evidence": evidence},
            "compliance": {"rating": rating, "evidence": evidence},
            "documentation": {"rating": rating, "evidence": evidence},
        },
        "red_flags": [],
    }


class CalculateScoreTests(unittest.TestCase):
    def test_perfect_startup_is_ready_with_full_confidence(self) -> None:
        result = score_module.calculate(startup_payload())
        self.assertEqual(result["raw_score"], 100.0)
        self.assertEqual(result["final_score"], 100.0)
        self.assertEqual(result["confidence_percent"], 100.0)
        self.assertEqual(result["readiness_band"], "ready")
        self.assertFalse(result["provisional"])

    def test_operating_company_uses_operating_weights(self) -> None:
        payload = operating_company_payload()
        payload["criteria"] = {
            "repayment_capacity": {"rating": 4, "evidence": "confirmed"},
            "financial_health": {"rating": 3, "evidence": "confirmed"},
            "business_viability": {"rating": 4, "evidence": "reported"},
            "borrowing_suitability": {"rating": 3, "evidence": "confirmed"},
            "compliance": {"rating": 5, "evidence": "reported"},
            "documentation": {"rating": 4, "evidence": "confirmed"},
        }
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 76.0)
        self.assertEqual(result["readiness_band"], "conditionally_ready")
        self.assertEqual(result["confidence_percent"], 88.0)

    def test_major_and_critical_caps_use_lowest_cap(self) -> None:
        payload = startup_payload()
        payload["red_flags"] = [
            {
                "code": "tax_or_social_insurance_arrears",
                "severity": "major",
                "evidence": "reported",
            },
            {"code": "material_misrepresentation", "severity": "critical", "evidence": "confirmed"},
        ]
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 100.0)
        self.assertEqual(result["final_score"], 39.0)
        self.assertEqual(result["applied_cap"], 39)
        self.assertEqual(result["readiness_band"], "significant_issues")

    def test_unknown_core_criterion_is_zero_and_provisional(self) -> None:
        payload = startup_payload()
        payload["criteria"]["funding_plan"] = {"rating": 5, "evidence": "unknown"}
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 80.0)
        self.assertEqual(result["criterion_points"]["funding_plan"], 0.0)
        self.assertTrue(result["provisional"])
        self.assertEqual(result["missing_core_criteria"], ["funding_plan"])

    def test_rejects_non_integer_ratings(self) -> None:
        for rating in (1.234, 3.0, True):
            with self.subTest(rating=rating):
                with self.assertRaisesRegex(ValueError, "integer"):
                    score_module.calculate(startup_payload(rating=rating))

    def test_raw_score_reconciles_to_displayed_criterion_points(self) -> None:
        payload = startup_payload(rating=0)
        ratings = {
            "business_plan": 1,
            "funding_plan": 2,
            "repayment_capacity": 3,
            "founder_capability": 4,
            "compliance": 5,
            "documentation": 1,
        }
        for criterion, rating in ratings.items():
            payload["criteria"][criterion]["rating"] = rating
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], round(sum(result["criterion_points"].values()), 1))

    def test_readiness_band_boundaries(self) -> None:
        cases = {
            49.9: "significant_issues",
            50.0: "improvement_priority",
            64.9: "improvement_priority",
            65.0: "conditionally_ready",
            79.9: "conditionally_ready",
            80.0: "ready",
        }
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(score_module.readiness_band(score), expected)

    def test_identical_inputs_produce_identical_outputs(self) -> None:
        payload = operating_company_payload(rating=3, evidence="reported")
        self.assertEqual(score_module.calculate(payload), score_module.calculate(payload))

    def test_confidence_exactly_sixty_is_not_provisional(self) -> None:
        result = score_module.calculate(startup_payload(evidence="reported"))
        self.assertEqual(result["confidence_percent"], 60.0)
        self.assertFalse(result["provisional"])

    def test_unknown_non_core_criterion_does_not_make_result_provisional(self) -> None:
        payload = startup_payload()
        payload["criteria"]["documentation"] = {"rating": 5, "evidence": "unknown"}
        result = score_module.calculate(payload)
        self.assertEqual(result["criterion_points"]["documentation"], 0.0)
        self.assertEqual(result["confidence_percent"], 95.0)
        self.assertFalse(result["provisional"])

    def test_criterion_ids_and_weights_drive_scores(self) -> None:
        cases = {
            "startup": {
                "business_plan": 25,
                "funding_plan": 20,
                "repayment_capacity": 20,
                "founder_capability": 15,
                "compliance": 15,
                "documentation": 5,
            },
            "operating_company": {
                "repayment_capacity": 30,
                "financial_health": 20,
                "business_viability": 15,
                "borrowing_suitability": 15,
                "compliance": 15,
                "documentation": 5,
            },
        }
        payload_builders = {
            "startup": startup_payload,
            "operating_company": operating_company_payload,
        }
        for mode, weights in cases.items():
            for criterion, expected_points in weights.items():
                with self.subTest(mode=mode, criterion=criterion):
                    payload = payload_builders[mode](rating=0)
                    payload["criteria"][criterion]["rating"] = 5
                    result = score_module.calculate(payload)
                    self.assertEqual(result["raw_score"], float(expected_points))
                    self.assertEqual(
                        result["criterion_points"][criterion], float(expected_points)
                    )

    def test_rejects_incomplete_criteria(self) -> None:
        payload = startup_payload()
        del payload["criteria"]["documentation"]
        with self.assertRaisesRegex(ValueError, "criteria must contain exactly"):
            score_module.calculate(payload)

    def test_rejects_out_of_range_rating(self) -> None:
        payload = startup_payload(rating=6)
        with self.assertRaisesRegex(ValueError, "rating"):
            score_module.calculate(payload)

    def test_rejects_unconfirmed_red_flag(self) -> None:
        payload = startup_payload()
        payload["red_flags"] = [
            {
                "code": "tax_or_social_insurance_arrears",
                "severity": "major",
                "evidence": "unknown",
            }
        ]
        with self.assertRaisesRegex(ValueError, "red flag evidence"):
            score_module.calculate(payload)

    def test_rejects_unknown_or_invalid_red_flag_code(self) -> None:
        for code in ("unknown_flag", "", 7):
            with self.subTest(code=code):
                payload = startup_payload()
                payload["red_flags"] = [
                    {"code": code, "severity": "major", "evidence": "confirmed"}
                ]
                with self.assertRaisesRegex(ValueError, "code must be a known nonempty string"):
                    score_module.calculate(payload)

    def test_rejects_red_flag_severity_that_conflicts_with_catalog(self) -> None:
        cases = (
            ("material_misrepresentation", "major"),
            ("tax_or_social_insurance_arrears", "critical"),
        )
        for code, severity in cases:
            with self.subTest(code=code, severity=severity):
                payload = startup_payload()
                payload["red_flags"] = [
                    {"code": code, "severity": severity, "evidence": "reported"}
                ]
                with self.assertRaisesRegex(ValueError, "severity must match the catalog"):
                    score_module.calculate(payload)

    def test_missing_license_accepts_both_catalog_severities(self) -> None:
        for severity, expected_cap in (("major", 59), ("critical", 39)):
            with self.subTest(severity=severity):
                payload = startup_payload()
                payload["red_flags"] = [
                    {
                        "code": "missing_required_license",
                        "severity": severity,
                        "evidence": "confirmed",
                    }
                ]
                result = score_module.calculate(payload)
                self.assertEqual(result["applied_cap"], expected_cap)

    def test_documented_red_flag_code_severity_mapping(self) -> None:
        cases = (
            ("current_serious_delinquency", "critical", 39),
            ("material_misrepresentation", "critical", 39),
            ("ineligible_or_illegal_use", "critical", 39),
            ("missing_required_license", "major", 59),
            ("missing_required_license", "critical", 39),
            ("tax_or_social_insurance_arrears", "major", 59),
            ("unsupported_debt_service", "major", 59),
            ("unexplained_material_inconsistency", "major", 59),
            ("unclear_use_of_funds", "major", 59),
        )
        for code, severity, expected_cap in cases:
            with self.subTest(code=code, severity=severity):
                payload = startup_payload()
                payload["red_flags"] = [
                    {"code": code, "severity": severity, "evidence": "confirmed"}
                ]
                self.assertEqual(score_module.calculate(payload)["applied_cap"], expected_cap)

    def test_cli_returns_json(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(startup_payload(), handle)
            handle.flush()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), handle.name],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result["final_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
