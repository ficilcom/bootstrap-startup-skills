from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/sales/customer-contract-terms-review/scripts/review_contract_terms.py"
SPEC = importlib.util.spec_from_file_location("review_contract_terms", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def days(value: float | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-28",
        "currency": "JPY",
        "contract": {
            "value": money(6_000_000),
            "duration_months": 6,
            "billing_schedule": [
                {"month_index": 1, "amount": money(2_000_000)},
                {"month_index": 4, "amount": money(2_000_000)},
                {"month_index": 6, "amount": money(2_000_000)},
            ],
            "payment_terms_days": days(60),
            "acceptance_lag_days": days(30),
            "delivery_cost_by_month": [money(700_000, "estimated") for _ in range(6)],
        },
        "policy_limits": {
            "max_payment_terms_days": days(45, "reported"),
            "max_uncovered_cost": money(1_500_000, "reported"),
        },
    }


def advanced() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["policy_limits"]["max_liability_cap_ratio"] = days(1.0, "reported")
    data["annual_revenue"] = money(30_000_000, "reported")
    data["terms"] = {
        "liability_cap": {"type": "capped", "amount": money(1_200_000)},
        "termination_notice_days": days(30),
        "auto_renewal": True,
        "renewal_term_months": 12,
        "ip_assignment": "assigned",
        "subcontracting": "prohibited",
    }
    return data


class ContractTermsReviewTests(unittest.TestCase):
    def test_converts_billing_into_receipts_and_finds_the_funding_peak(self) -> None:
        result = MODULE.calculate(payload())
        cash = result["cash_path"]

        self.assertEqual(cash["months"], 9)
        self.assertEqual(cash["receipt_month_offset"], 3)
        self.assertEqual(cash["days_to_first_cash"], 90)
        self.assertEqual(cash["peak_funded_amount"], 2_200_000)
        self.assertEqual(cash["peak_funded_month"], 6)
        self.assertEqual(cash["final_cumulative_cash"], 1_800_000)
        self.assertEqual(cash["cumulative_cash"][3], -800_000)
        self.assertEqual(
            result["review_scope"],
            "cash timing and monetary exposure from stated commercial terms only; clause validity, enforceability, legal risk, price level, and customer relationship remain separate",
        )

    def test_reports_breached_and_unset_policy_limits(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["breached_policy_limits"], ["max_payment_terms_days", "max_uncovered_cost"])
        self.assertEqual(result["policies_not_set"], ["max_liability_cap_ratio"])

    def test_unknown_delivery_cost_truncates_without_becoming_zero(self) -> None:
        data = payload()
        data["contract"]["delivery_cost_by_month"][3] = money(None, "unknown")

        result = MODULE.calculate(data)
        cash = result["cash_path"]

        self.assertEqual(cash["cumulative_cash"][2], -2_100_000)
        self.assertIsNone(cash["cumulative_cash"][3])
        self.assertEqual(cash["peak_funded_amount"], 2_100_000)
        self.assertEqual(cash["peak_funded_month"], 3)
        self.assertIsNone(cash["final_cumulative_cash"])
        self.assertEqual(cash["days_to_first_cash"], 90)
        self.assertIn("max_uncovered_cost", result["breached_policy_limits"])
        self.assertIn("cash_path_truncated_at_month_4", result["analysis_quality"]["warnings"])
        self.assertIn("contract.delivery_cost_by_month[3]", result["analysis_quality"]["decision_changing_unknowns"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_advanced_quantifies_liability_termination_and_renewal(self) -> None:
        result = MODULE.calculate(advanced())

        self.assertEqual(result["liability"]["cap_type"], "capped")
        self.assertEqual(result["liability"]["cap_to_contract_value_ratio"], 0.2)
        self.assertEqual(result["liability"]["cap_to_annual_revenue_ratio"], 0.04)
        self.assertEqual(result["termination"]["earliest_termination_month"], 2)
        self.assertEqual(result["termination"]["unrecovered_cost_at_earliest_termination"], 1_400_000)
        self.assertEqual(result["termination"]["committed_months"], 18)
        self.assertEqual(
            [entry["clause"] for entry in result["negotiation_priorities"]],
            ["payment_terms", "termination_notice", "liability_cap"],
        )
        self.assertIn("auto_renewal_extends_commitment", result["clause_flags"])
        self.assertIn("ip_assigned_to_customer", result["clause_flags"])
        self.assertIn("subcontracting_prohibited", result["clause_flags"])

    def test_uncapped_liability_breaches_and_ranks_first(self) -> None:
        data = advanced()
        data["terms"]["liability_cap"] = {"type": "uncapped"}

        result = MODULE.calculate(data)

        self.assertIsNone(result["liability"]["cap_to_contract_value_ratio"])
        self.assertIn("max_liability_cap_ratio", result["breached_policy_limits"])
        self.assertIn("liability_uncapped", result["clause_flags"])
        self.assertEqual(result["negotiation_priorities"][0]["clause"], "liability_cap")
        self.assertIsNone(result["negotiation_priorities"][0]["exposure"])

    def test_unknown_liability_cap_is_not_treated_as_uncapped(self) -> None:
        data = advanced()
        data["terms"]["liability_cap"] = {"type": "unknown"}

        result = MODULE.calculate(data)

        self.assertEqual(result["liability"]["cap_type"], "unknown")
        self.assertNotIn("max_liability_cap_ratio", result["breached_policy_limits"])
        self.assertNotIn("liability_uncapped", result["clause_flags"])
        self.assertIn("terms.liability_cap", result["analysis_quality"]["decision_changing_unknowns"])

    def test_core_mode_ignores_advanced_sections(self) -> None:
        data = advanced()
        data["analysis_mode"] = "core"

        result = MODULE.calculate(data)

        self.assertEqual(result["liability"], {})
        self.assertEqual(result["negotiation_priorities"], [])
        self.assertEqual(result["clause_flags"], [])

    def test_warns_when_billing_does_not_match_contract_value(self) -> None:
        data = payload()
        data["contract"]["billing_schedule"][2]["amount"] = money(1_000_000)

        result = MODULE.calculate(data)

        self.assertIn("billing_schedule_does_not_match_contract_value", result["analysis_quality"]["warnings"])

    def test_rejects_duplicate_months_bad_ranges_and_invalid_enums(self) -> None:
        data = payload()
        data["contract"]["billing_schedule"][1]["month_index"] = 1
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["contract"]["billing_schedule"][1]["month_index"] = 7
        with self.assertRaisesRegex(ValueError, "month_index"):
            MODULE.calculate(data)

        data = advanced()
        data["terms"]["ip_assignment"] = "shared"
        with self.assertRaisesRegex(ValueError, "ip_assignment"):
            MODULE.calculate(data)

        data = advanced()
        data["terms"]["liability_cap"] = {"type": "uncapped", "amount": money(1)}
        with self.assertRaisesRegex(ValueError, "null"):
            MODULE.calculate(data)

    def test_rejects_wrong_series_length_currency_and_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["contract"]["delivery_cost_by_month"] = [money(1)]
        with self.assertRaisesRegex(ValueError, "duration_months entries"):
            MODULE.calculate(data)

        data = payload()
        data["contract"]["value"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["contract"]["payment_terms_days"] = days(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(advanced()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["cash_path"]["peak_funded_amount"], 2_200_000)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
