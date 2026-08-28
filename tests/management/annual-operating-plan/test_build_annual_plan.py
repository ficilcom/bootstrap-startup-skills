from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/management/annual-operating-plan/scripts/build_annual_plan.py"
SPEC = importlib.util.spec_from_file_location("build_annual_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount: int | None, evidence: str = "confirmed") -> dict[str, object]:
    return {"amount": amount, "currency": "JPY", "evidence": evidence}


def scalar(value: float | None, evidence: str = "reported") -> dict[str, object]:
    return {"value": value, "evidence": evidence}


def series(amount: int, evidence: str = "reported") -> list[dict[str, object]]:
    return [money(amount, evidence) for _ in range(12)]


def payload() -> dict[str, object]:
    return {
        "fiscal_year_start": "2026-04-01",
        "currency": "JPY",
        "opening_cash": money(6_000_000),
        "minimum_cash_buffer": money(3_000_000, "reported"),
        "revenue_streams": [
            {
                "id": "subscription",
                "monthly_revenue": series(1_000_000, "estimated"),
                "gross_margin_rate": scalar(0.6),
            }
        ],
        "fixed_costs_by_month": series(500_000),
        "committed_outflows": [
            {"name": "consumption-tax", "month_index": 3, "amount": money(1_200_000)},
            {"name": "loan-repayment", "month_index": 9, "amount": money(800_000)},
        ],
        "annual_targets": {
            "revenue": money(15_000_000, "reported"),
            "gross_profit": money(7_000_000, "reported"),
            "ending_cash": money(8_000_000, "reported"),
        },
    }


def advanced() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["scenarios"] = [
        {
            "id": "downside",
            "revenue_multiplier": scalar(0.8, "estimated"),
            "margin_delta": scalar(-0.05, "estimated"),
            "cost_multiplier": scalar(1.1, "estimated"),
        }
    ]
    data["quarterly_checkpoints"] = [
        {"quarter": 1, "metric": "revenue", "threshold": money(3_000_000, "reported"), "revision_trigger": "下回れば獲得計画を再設計"},
        {"quarter": 3, "metric": "ending_cash", "threshold": money(5_000_000, "reported"), "revision_trigger": "下回れば固定費を再査定"},
    ]
    return data


class AnnualOperatingPlanTests(unittest.TestCase):
    def test_builds_monthly_quarterly_and_annual_plan(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["annual"]["revenue"], 12_000_000)
        self.assertEqual(result["annual"]["gross_profit"], 7_200_000)
        self.assertEqual(result["annual"]["ending_cash"], 5_200_000)
        self.assertEqual(result["cash_path"]["minimum_cash"], 4_900_000)
        self.assertIsNone(result["cash_path"]["buffer_breach_month"])
        self.assertEqual(result["cash_path"]["monthly_ending_cash"][2], 5_100_000)

        quarters = {item["quarter"]: item for item in result["quarters"]}
        self.assertEqual(quarters[1]["net_cash"], -900_000)
        self.assertEqual(quarters[3]["ending_cash"], 4_900_000)
        self.assertEqual(quarters[4]["gross_profit"], 1_800_000)

    def test_target_reach_is_arithmetic_and_separate_from_cash_survival(self) -> None:
        result = MODULE.calculate(payload())
        targets = result["target_assessment"]

        self.assertFalse(targets["revenue"]["reaches_target"])
        self.assertEqual(targets["revenue"]["shortfall"], 3_000_000)
        self.assertTrue(targets["gross_profit"]["reaches_target"])
        self.assertEqual(targets["gross_profit"]["shortfall"], 0)
        self.assertEqual(targets["ending_cash"]["shortfall"], 2_800_000)
        self.assertEqual(result["required_additional_gross_profit"], 2_800_000)
        self.assertEqual(
            result["planning_scope"],
            "arithmetic reach of user-supplied assumptions and cash survivability only; target achievability, demand, capacity, and execution remain separate",
        )

    def test_reports_first_buffer_breach_month(self) -> None:
        data = payload()
        data["opening_cash"] = money(4_000_000)

        result = MODULE.calculate(data)

        self.assertEqual(result["cash_path"]["buffer_breach_month"], 9)
        self.assertEqual(result["cash_path"]["minimum_cash"], 2_900_000)

    def test_unknown_month_truncates_cash_path_without_zeroing(self) -> None:
        data = payload()
        data["revenue_streams"][0]["monthly_revenue"][4] = money(None, "unknown")

        result = MODULE.calculate(data)
        quarters = {item["quarter"]: item for item in result["quarters"]}

        self.assertEqual(result["cash_path"]["monthly_ending_cash"][3], 5_200_000)
        self.assertIsNone(result["cash_path"]["monthly_ending_cash"][4])
        self.assertIsNone(result["annual"]["revenue"])
        self.assertIsNone(result["annual"]["ending_cash"])
        self.assertIsNone(result["target_assessment"]["ending_cash"]["reaches_target"])
        self.assertEqual(quarters[1]["revenue"], 3_000_000)
        self.assertIsNone(quarters[2]["revenue"])
        self.assertIn("cash_path_truncated_at_month_5", result["analysis_quality"]["warnings"])
        self.assertIn("revenue_streams[0].monthly_revenue[4]", result["analysis_quality"]["decision_changing_unknowns"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_advanced_scenarios_and_checkpoints(self) -> None:
        result = MODULE.calculate(advanced())
        scenario = {item["id"]: item for item in result["scenarios"]}["downside"]

        self.assertEqual(scenario["annual_revenue"], 9_600_000)
        self.assertEqual(scenario["annual_gross_profit"], 5_280_000)
        self.assertEqual(scenario["ending_cash"], 2_680_000)
        self.assertEqual(scenario["buffer_breach_month"], 10)

        checkpoints = {(item["quarter"], item["metric"]): item for item in result["checkpoints"]}
        self.assertTrue(checkpoints[(1, "revenue")]["meets_threshold"])
        self.assertFalse(checkpoints[(3, "ending_cash")]["meets_threshold"])
        self.assertEqual(checkpoints[(3, "ending_cash")]["planned_value"], 4_900_000)
        self.assertEqual(result["analysis_quality"]["mode"], "advanced")

    def test_core_mode_ignores_advanced_sections(self) -> None:
        data = advanced()
        data["analysis_mode"] = "core"

        result = MODULE.calculate(data)

        self.assertEqual(result["scenarios"], [])
        self.assertEqual(result["checkpoints"], [])

    def test_rejects_duplicate_ids_bad_months_and_invalid_margins(self) -> None:
        data = payload()
        data["revenue_streams"].append(dict(data["revenue_streams"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["committed_outflows"][0]["month_index"] = 13
        with self.assertRaisesRegex(ValueError, "month_index"):
            MODULE.calculate(data)

        data = payload()
        data["revenue_streams"][0]["gross_margin_rate"] = scalar(1.4)
        with self.assertRaisesRegex(ValueError, "gross_margin_rate"):
            MODULE.calculate(data)

        data = advanced()
        data["quarterly_checkpoints"].append(dict(data["quarterly_checkpoints"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

    def test_rejects_wrong_series_length_currency_and_unknown_encoded_as_zero(self) -> None:
        data = payload()
        data["fixed_costs_by_month"] = [money(1)]
        with self.assertRaisesRegex(ValueError, "12 entries"):
            MODULE.calculate(data)

        data = payload()
        data["opening_cash"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

        data = payload()
        data["minimum_cash_buffer"] = money(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(advanced()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["annual"]["gross_profit"], 7_200_000)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
