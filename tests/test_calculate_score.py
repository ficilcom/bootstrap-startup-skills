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


class CalculateScoreTests(unittest.TestCase):
    def test_perfect_startup_is_ready_with_full_confidence(self) -> None:
        result = score_module.calculate(startup_payload())
        self.assertEqual(result["raw_score"], 100.0)
        self.assertEqual(result["final_score"], 100.0)
        self.assertEqual(result["confidence_percent"], 100.0)
        self.assertEqual(result["readiness_band"], "ready")
        self.assertFalse(result["provisional"])

    def test_operating_company_uses_operating_weights(self) -> None:
        payload = {
            "mode": "operating_company",
            "criteria": {
                "repayment_capacity": {"rating": 4, "evidence": "confirmed"},
                "financial_health": {"rating": 3, "evidence": "confirmed"},
                "business_viability": {"rating": 4, "evidence": "reported"},
                "borrowing_suitability": {"rating": 3, "evidence": "confirmed"},
                "compliance": {"rating": 5, "evidence": "reported"},
                "documentation": {"rating": 4, "evidence": "confirmed"},
            },
            "red_flags": [],
        }
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 76.0)
        self.assertEqual(result["readiness_band"], "conditionally_ready")
        self.assertEqual(result["confidence_percent"], 88.0)

    def test_major_and_critical_caps_use_lowest_cap(self) -> None:
        payload = startup_payload()
        payload["red_flags"] = [
            {"code": "tax_arrears", "severity": "major", "evidence": "reported"},
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

    def test_scores_are_rounded_to_one_decimal_place(self) -> None:
        result = score_module.calculate(startup_payload(rating=1.234))
        self.assertEqual(result["criterion_points"]["business_plan"], 6.2)
        self.assertEqual(result["raw_score"], 24.7)

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
            {"code": "possible_arrears", "severity": "major", "evidence": "unknown"}
        ]
        with self.assertRaisesRegex(ValueError, "red flag evidence"):
            score_module.calculate(payload)

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
