from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/sales/sales-forecast-confidence/scripts/calculate_sales_forecast.py"
SPEC = importlib.util.spec_from_file_location("calculate_sales_forecast", SCRIPT)
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
        "forecast_period": "2026-Q4",
        "target": money(1_000_000, "reported"),
        "minimum_stage_sample": 10,
        "history": [
            {"period": "Q1", "forecast": money(800_000), "actual": money(1_000_000)},
            {"period": "Q2", "forecast": money(1_200_000), "actual": money(1_000_000)},
        ],
        "stages": [
            {
                "name": "proposal",
                "open_amount": money(1_000_000),
                "deal_count": scalar(5),
                "historical_win_rate": scalar(0.4, "reported"),
                "low_win_rate": scalar(0.3, "estimated"),
                "high_win_rate": scalar(0.5, "estimated"),
                "historical_sample": scalar(20),
            },
            {
                "name": "negotiation",
                "open_amount": money(500_000),
                "deal_count": scalar(2),
                "historical_win_rate": scalar(0.8, "reported"),
                "low_win_rate": scalar(0.6, "estimated"),
                "high_win_rate": scalar(0.9, "estimated"),
                "historical_sample": scalar(8),
            },
        ],
    }


class SalesForecastTests(unittest.TestCase):
    def test_calculates_historical_error_bias_and_pipeline_range(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["history"]["wape"], 0.2)
        self.assertEqual(result["history"]["bias_rate"], 0)
        self.assertEqual(result["forecast"]["weighted_amount"], 800_000)
        self.assertEqual(result["forecast"]["low_amount"], 600_000)
        self.assertEqual(result["forecast"]["high_amount"], 950_000)
        self.assertEqual(result["forecast"]["target_gap"], 200_000)
        self.assertEqual(result["forecast"]["coverage_rate"], 0.8)

    def test_stage_output_exposes_rates_and_weighted_amount(self) -> None:
        stage = MODULE.calculate(payload())["stages"][0]

        self.assertEqual(stage["weighted_amount"], 400_000)
        self.assertEqual(stage["low_amount"], 300_000)
        self.assertEqual(stage["high_amount"], 500_000)

    def test_small_stage_sample_is_flagged_without_changing_rate(self) -> None:
        stage = MODULE.calculate(payload())["stages"][1]

        self.assertIn("small_historical_sample", stage["flags"])
        self.assertEqual(stage["weighted_amount"], 400_000)

    def test_unknown_core_stage_input_keeps_forecast_indeterminate(self) -> None:
        data = payload()
        data["stages"][0]["historical_win_rate"] = scalar(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["stages"][0]["status"], "indeterminate")
        self.assertEqual(result["forecast"]["status"], "indeterminate")
        self.assertIsNone(result["forecast"]["weighted_amount"])
        self.assertIn("stages[0].historical_win_rate", result["missing_inputs"])

    def test_zero_actual_history_does_not_invent_error_rate(self) -> None:
        data = payload()
        data["history"] = [{"period": "Q1", "forecast": money(100), "actual": money(0)}]

        history = MODULE.calculate(data)["history"]

        self.assertIsNone(history["wape"])
        self.assertIn("zero_historical_actual", history["flags"])

    def test_rejects_duplicate_stages_invalid_ranges_and_currency(self) -> None:
        data = payload()
        data["stages"][1]["name"] = "proposal"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["stages"][0]["low_win_rate"] = scalar(0.6)
        with self.assertRaisesRegex(ValueError, "low.*historical.*high"):
            MODULE.calculate(data)

        data = payload()
        data["target"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero_and_nonpositive_sample_threshold(self) -> None:
        data = payload()
        data["stages"][0]["deal_count"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["minimum_stage_sample"] = 0
        with self.assertRaisesRegex(ValueError, "positive integer"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["forecast"]["weighted_amount"], 800_000)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
