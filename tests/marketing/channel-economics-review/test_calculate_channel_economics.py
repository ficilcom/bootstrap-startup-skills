from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/marketing/channel-economics-review/scripts/calculate_channel_economics.py"
SPEC = importlib.util.spec_from_file_location("calculate_channel_economics", SCRIPT)
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
        "period_unit": "month",
        "horizon_periods": 6,
        "channels": [
            {
                "name": "paid-search",
                "spend": money(120_000),
                "acquired_customers": scalar(12),
                "contribution_per_customer_per_period": money(4_000),
                "retention_rate_per_period": scalar(1),
                "capacity_new_customers": scalar(20, "reported"),
                "marginal_case": {
                    "incremental_spend": money(40_000, "estimated"),
                    "incremental_customers": scalar(2, "estimated"),
                },
            },
            {
                "name": "partners",
                "spend": money(60_000),
                "acquired_customers": scalar(4),
                "contribution_per_customer_per_period": money(8_000),
                "retention_rate_per_period": scalar(1),
                "capacity_new_customers": scalar(5, "reported"),
                "marginal_case": {
                    "incremental_spend": money(20_000, "estimated"),
                    "incremental_customers": scalar(2, "estimated"),
                },
            },
        ],
    }


class ChannelEconomicsTests(unittest.TestCase):
    def test_calculates_blended_and_marginal_economics(self) -> None:
        result = MODULE.calculate(payload())
        channels = {item["name"]: item for item in result["channels"]}

        self.assertEqual(channels["paid-search"]["cac"], 10_000)
        self.assertEqual(channels["paid-search"]["payback_periods"], 3)
        self.assertEqual(channels["paid-search"]["horizon_contribution"], 288_000)
        self.assertEqual(channels["paid-search"]["horizon_net_contribution"], 168_000)
        self.assertEqual(channels["paid-search"]["marginal_cac"], 20_000)
        self.assertEqual(channels["paid-search"]["marginal_payback_periods"], 5)
        self.assertEqual(channels["partners"]["marginal_horizon_net_contribution"], 76_000)
        self.assertEqual(result["economic_order"], ["partners", "paid-search"])

    def test_retention_reduces_contribution_without_becoming_churn_forecast(self) -> None:
        data = payload()
        channel = data["channels"][0]
        channel["spend"] = money(7_000)
        channel["acquired_customers"] = scalar(1)
        channel["contribution_per_customer_per_period"] = money(4_000)
        channel["retention_rate_per_period"] = scalar(0.5, "estimated")
        data["channels"] = [channel]

        result = MODULE.calculate(data)["channels"][0]

        self.assertEqual(result["horizon_contribution"], 7_875)
        self.assertEqual(result["payback_periods"], 3)

    def test_zero_acquisitions_do_not_invent_cac_or_payback(self) -> None:
        data = payload()
        data["channels"][0]["acquired_customers"] = scalar(0)

        result = MODULE.calculate(data)["channels"][0]

        self.assertIsNone(result["cac"])
        self.assertIsNone(result["payback_periods"])
        self.assertIn("zero_acquisitions", result["flags"])

    def test_unknown_core_input_keeps_channel_indeterminate(self) -> None:
        data = payload()
        data["channels"][0]["spend"] = money(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["channels"][0]["status"], "indeterminate")
        self.assertNotIn("paid-search", result["economic_order"])
        self.assertIn("channels[0].spend", result["missing_inputs"])

    def test_flags_capacity_constraint_separately_from_economics(self) -> None:
        data = payload()
        data["channels"][1]["capacity_new_customers"] = scalar(1, "reported")

        result = MODULE.calculate(data)["channels"][1]

        self.assertIn("capacity_exceeded", result["flags"])
        self.assertEqual(result["horizon_net_contribution"], 132_000)

    def test_rejects_duplicate_channels_invalid_retention_and_currency(self) -> None:
        data = payload()
        data["channels"][1]["name"] = "paid-search"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["channels"][0]["retention_rate_per_period"] = scalar(1.1)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            MODULE.calculate(data)

        data = payload()
        data["channels"][0]["spend"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero_and_nonpositive_horizon(self) -> None:
        data = payload()
        data["channels"][0]["acquired_customers"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["horizon_periods"] = 0
        with self.assertRaisesRegex(ValueError, "positive integer"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["economic_order"][0], "partners")

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
