from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/marketing/customer-retention-review/scripts/calculate_retention.py"
SPEC = importlib.util.spec_from_file_location("calculate_retention", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "cohort": {"start_date": "2026-05-01", "end_date": "2026-07-31"},
        "renewal_horizon_days": 90,
        "customers": [
            {
                "id": "a",
                "segment": "startup",
                "start_recurring_revenue": money(100_000),
                "end_recurring_revenue": money(120_000),
                "status": "active",
            },
            {
                "id": "b",
                "segment": "startup",
                "start_recurring_revenue": money(80_000),
                "end_recurring_revenue": money(60_000),
                "status": "active",
            },
            {
                "id": "c",
                "segment": "agency",
                "start_recurring_revenue": money(20_000),
                "end_recurring_revenue": money(0),
                "status": "churned",
                "churn_reason": "budget",
                "churn_reason_evidence": "customer_stated",
            },
        ],
        "renewals": [
            {
                "customer_id": "a",
                "renewal_date": "2026-09-21",
                "recurring_revenue": money(120_000),
                "risk_signals": ["usage_decline", "no_next_step"],
                "risk_evidence": "reported",
            },
            {
                "customer_id": "b",
                "renewal_date": "2026-12-01",
                "recurring_revenue": money(60_000),
                "risk_signals": [],
                "risk_evidence": "confirmed",
            },
        ],
    }


class RetentionTests(unittest.TestCase):
    def test_calculates_logo_grr_nrr_and_revenue_movements(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["logo_retention"], 0.666667)
        self.assertEqual(result["gross_revenue_retention"], 0.8)
        self.assertEqual(result["net_revenue_retention"], 0.9)
        self.assertEqual(result["starting_recurring_revenue"], 200_000)
        self.assertEqual(result["ending_recurring_revenue"], 180_000)
        self.assertEqual(result["expansion_revenue"], 20_000)
        self.assertEqual(result["contraction_revenue"], 20_000)
        self.assertEqual(result["churned_revenue"], 20_000)
        self.assertEqual(result["churn_reasons"], [{"reason": "budget", "count": 1}])

    def test_limits_renewal_exposure_to_horizon_and_preserves_signals(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["renewal_exposure"], 120_000)
        self.assertEqual(result["renewals_needing_attention"], ["a"])
        self.assertEqual(result["renewals"][0]["days_to_renewal"], 30)
        self.assertEqual(result["renewals"][0]["signal_count"], 2)

    def test_overdue_renewal_is_not_silently_treated_as_churn(self) -> None:
        data = payload()
        data["renewals"][0]["renewal_date"] = "2026-08-01"

        result = MODULE.calculate(data)

        self.assertIn("renewal_overdue", result["renewals"][0]["flags"])
        self.assertEqual(result["customers"][0]["status"], "active")

    def test_unknown_revenue_keeps_financial_retention_indeterminate(self) -> None:
        data = payload()
        data["customers"][1]["end_recurring_revenue"] = money(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["financial_status"], "indeterminate")
        self.assertIsNone(result["gross_revenue_retention"])
        self.assertEqual(result["logo_retention"], 0.666667)
        self.assertIn("customers[1].end_recurring_revenue", result["missing_inputs"])

    def test_zero_starting_revenue_does_not_invent_revenue_rates(self) -> None:
        data = payload()
        for customer in data["customers"]:
            customer["start_recurring_revenue"] = money(0)
            customer["end_recurring_revenue"] = money(0)

        result = MODULE.calculate(data)

        self.assertIsNone(result["gross_revenue_retention"])
        self.assertIsNone(result["net_revenue_retention"])

    def test_rejects_duplicate_customers_invalid_churn_and_unknown_renewal_customer(self) -> None:
        data = payload()
        data["customers"][1]["id"] = "a"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["customers"][2]["end_recurring_revenue"] = money(1)
        with self.assertRaisesRegex(ValueError, "churned"):
            MODULE.calculate(data)

        data = payload()
        data["renewals"][0]["customer_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "customer"):
            MODULE.calculate(data)

    def test_rejects_invalid_dates_signals_currency_and_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["cohort"]["end_date"] = "2026-08-23"
        with self.assertRaisesRegex(ValueError, "as_of_date"):
            MODULE.calculate(data)

        data = payload()
        data["renewals"][0]["risk_signals"] = ["invented"]
        with self.assertRaisesRegex(ValueError, "risk signal"):
            MODULE.calculate(data)

        data = payload()
        data["customers"][0]["start_recurring_revenue"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["customers"][0]["start_recurring_revenue"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["net_revenue_retention"], 0.9)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
