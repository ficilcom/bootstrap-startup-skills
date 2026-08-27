from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/finance/accounts-receivable-control/scripts/analyze_receivables.py"
SPEC = importlib.util.spec_from_file_location("analyze_receivables", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def payload() -> dict[str, object]:
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "cash_context": {
            "available_cash": money(300_000),
            "minimum_cash_buffer": money(250_000),
            "near_term_obligations": money(100_000),
        },
        "invoices": [
            {
                "id": "inv-1",
                "customer_id": "customer-a",
                "issued_date": "2026-06-01",
                "due_date": "2026-06-30",
                "original_amount": money(200_000),
                "paid_amount": money(50_000),
                "payment_commitment": {"date": "2026-08-25", "amount": money(100_000)},
                "disputed": False,
            },
            {
                "id": "inv-2",
                "customer_id": "customer-b",
                "issued_date": "2026-07-01",
                "due_date": "2026-07-31",
                "original_amount": money(80_000),
                "paid_amount": money(0),
                "payment_commitment": {
                    "date": "2026-08-30",
                    "amount": money(80_000, "reported"),
                },
                "disputed": True,
            },
            {
                "id": "inv-3",
                "customer_id": "customer-a",
                "issued_date": "2026-08-10",
                "due_date": "2026-09-10",
                "original_amount": money(50_000),
                "paid_amount": money(0),
                "disputed": False,
            },
        ],
    }


class AnalyzeReceivablesTests(unittest.TestCase):
    def test_calculates_outstanding_aging_and_customer_exposure(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["known_outstanding"], 280_000)
        self.assertEqual(
            result["aging_buckets"],
            {"current": 50_000, "days_1_30": 80_000, "days_31_60": 150_000, "days_61_90": 0, "over_90": 0},
        )
        self.assertEqual(result["customers"][0]["customer_id"], "customer-a")
        self.assertEqual(result["customers"][0]["known_outstanding"], 200_000)
        self.assertEqual(result["customers"][0]["share_of_known_outstanding"], 0.714286)

    def test_cash_impact_uses_confirmed_commitments_only(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["commitments_by_evidence"], {"confirmed": 100_000, "reported": 80_000, "estimated": 0})
        self.assertEqual(
            result["cash_impact"],
            {
                "cash_before_receipts": 200_000,
                "buffer_gap_before_receipts": 50_000,
                "cash_after_confirmed_commitments": 300_000,
                "buffer_gap_after_confirmed_commitments": 0,
            },
        )

    def test_flags_disputes_and_missed_commitments_without_inventing_priority_score(self) -> None:
        data = payload()
        data["invoices"][0]["payment_commitment"]["date"] = "2026-08-10"

        result = MODULE.calculate(data)
        invoices = {item["id"]: item for item in result["invoices"]}

        self.assertEqual(invoices["inv-1"]["flags"], ["commitment_missed", "over_30_days_past_due"])
        self.assertEqual(invoices["inv-2"]["flags"], ["disputed"])

    def test_unknown_core_amount_makes_aggregate_indeterminate(self) -> None:
        data = payload()
        data["invoices"][2]["original_amount"] = money(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["status"], "indeterminate")
        self.assertIn("invoices[2].original_amount", result["missing_inputs"])
        self.assertIsNone(result["total_outstanding"])
        self.assertEqual(result["known_outstanding"], 230_000)

    def test_rejects_invalid_invoice_dates_and_duplicate_ids(self) -> None:
        data = payload()
        data["invoices"][1]["id"] = "inv-1"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["invoices"][0]["due_date"] = "2026-05-31"
        with self.assertRaisesRegex(ValueError, "issued_date"):
            MODULE.calculate(data)

        data = payload()
        data["invoices"][0]["issued_date"] = "2026-08-23"
        with self.assertRaisesRegex(ValueError, "as_of_date"):
            MODULE.calculate(data)

    def test_rejects_overpayment_currency_mismatch_and_excess_commitment(self) -> None:
        data = payload()
        data["invoices"][0]["paid_amount"] = money(250_000)
        with self.assertRaisesRegex(ValueError, "paid_amount"):
            MODULE.calculate(data)

        data = payload()
        data["invoices"][0]["original_amount"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["invoices"][0]["payment_commitment"]["amount"] = money(160_000)
        with self.assertRaisesRegex(ValueError, "outstanding"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["invoices"][0]["original_amount"] = money(0, "unknown")

        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_reports_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["known_outstanding"], 280_000)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
