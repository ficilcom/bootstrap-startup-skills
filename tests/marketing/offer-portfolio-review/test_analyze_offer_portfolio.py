from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/marketing/offer-portfolio-review/scripts/analyze_offer_portfolio.py"
SPEC = importlib.util.spec_from_file_location("analyze_offer_portfolio", SCRIPT)
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
        "period": "2026-Q3",
        "available_delivery_hours": scalar(200),
        "thresholds": {"minimum_margin_rate": 0.3, "capacity_heavy_share": 0.5},
        "offers": [
            {
                "name": "advisory",
                "revenue": money(1_000_000),
                "variable_cost": money(300_000),
                "delivery_hours": scalar(100),
                "strategic_fit": scalar(5, "reported"),
            },
            {
                "name": "workshop",
                "revenue": money(400_000),
                "variable_cost": money(100_000),
                "delivery_hours": scalar(50),
                "strategic_fit": scalar(3, "reported"),
            },
        ],
    }


def advanced_payload() -> dict[str, object]:
    data = payload()
    data["analysis_mode"] = "advanced"
    data["as_of_date"] = "2026-08-27"
    data["offers"][0].update({
        "demand": {"qualified_pipeline": money(500_000), "backlog_units": scalar(3), "lost_due_capacity_units": scalar(1), "renewal_rate": scalar(0.8)},
        "exit_constraints": {"active_contracts": scalar(2), "committed_revenue": money(200_000), "transition_cost": money(50_000), "earliest_exit_date": "2027-01-01"},
    })
    data["offers"][1].update({
        "demand": {"qualified_pipeline": money(None, "unknown"), "backlog_units": scalar(None, "unknown"), "lost_due_capacity_units": scalar(0), "renewal_rate": scalar(None, "unknown")},
        "exit_constraints": {"active_contracts": scalar(0), "committed_revenue": money(0), "transition_cost": money(0), "earliest_exit_date": "2026-08-01"},
    })
    data["relationships"] = [{"source": "workshop", "target": "advisory", "type": "cross_sell", "evidence": "reported"}]
    data["scenarios"] = [{
        "name": "downside",
        "offer_adjustments": [
            {"name": "advisory", "revenue_factor": scalar(0.8, "estimated"), "variable_cost_factor": scalar(1.2, "estimated"), "delivery_hours_factor": scalar(1.1, "estimated")},
            {"name": "workshop", "revenue_factor": scalar(1), "variable_cost_factor": scalar(1), "delivery_hours_factor": scalar(1)},
        ],
    }]
    return data


class OfferPortfolioTests(unittest.TestCase):
    def test_core_mode_adds_quality_without_changing_economics(self) -> None:
        result = MODULE.calculate(payload())

        self.assertEqual(result["analysis_quality"]["mode"], "core")
        self.assertEqual(result["analysis_quality"]["status"], "complete")
        self.assertEqual(result["offers"][0]["contribution"], 700_000)

    def test_advanced_mode_reports_demand_exit_gates_and_decision_signals(self) -> None:
        result = MODULE.calculate(advanced_payload())
        offers = {item["name"]: item for item in result["offers"]}

        self.assertEqual(offers["advisory"]["exit_gate"], "blocked")
        self.assertIn("grow_candidate", offers["advisory"]["decision_signals"])
        self.assertEqual(offers["workshop"]["demand_status"], "unknown")
        self.assertIn("test_candidate", offers["workshop"]["decision_signals"])
        self.assertEqual(result["analysis_quality"]["status"], "partial")

    def test_advanced_scenario_recalculates_economics_and_capacity(self) -> None:
        scenario = MODULE.calculate(advanced_payload())["scenario_metrics"][0]
        advisory = scenario["offers"]["advisory"]

        self.assertEqual(advisory["contribution"], 440_000)
        self.assertEqual(advisory["contribution_per_delivery_hour"], 4_000)
        self.assertEqual(scenario["total_delivery_hours"], 160)
        self.assertEqual(scenario["capacity_gap_hours"], 0)

    def test_advanced_relationships_remain_separate_from_offer_profit(self) -> None:
        result = MODULE.calculate(advanced_payload())

        self.assertEqual(result["relationships"][0]["type"], "cross_sell")
        self.assertIn("relationship_not_verified", result["relationships"][0]["flags"])
        self.assertIn("bundle_candidate", {item["name"]: item for item in result["offers"]}["workshop"]["decision_signals"])
        self.assertEqual(result["offers"][1]["contribution"], 300_000)

    def test_advanced_mode_rejects_unknown_relationships_bad_factors_and_dates(self) -> None:
        data = advanced_payload()
        data["relationships"][0]["target"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown offer"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["scenarios"][0]["offer_adjustments"][0]["revenue_factor"] = scalar(-1)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            MODULE.calculate(data)

        data = advanced_payload()
        data["offers"][0]["exit_constraints"]["earliest_exit_date"] = "01-01-2027"
        with self.assertRaisesRegex(ValueError, "ISO date"):
            MODULE.calculate(data)

    def test_calculates_offer_contribution_margin_and_hour_economics(self) -> None:
        result = MODULE.calculate(payload())
        offers = {item["name"]: item for item in result["offers"]}

        self.assertEqual(offers["advisory"]["contribution"], 700_000)
        self.assertEqual(offers["advisory"]["contribution_margin_rate"], 0.7)
        self.assertEqual(offers["advisory"]["contribution_per_delivery_hour"], 7_000)
        self.assertEqual(offers["advisory"]["capacity_share"], 0.5)
        self.assertEqual(result["portfolio"]["total_contribution"], 1_000_000)
        self.assertEqual(result["economic_order"], ["advisory", "workshop"])

    def test_flags_loss_making_low_margin_and_capacity_heavy_offers(self) -> None:
        data = payload()
        data["offers"][0]["variable_cost"] = money(1_100_000)
        data["offers"][0]["delivery_hours"] = scalar(150)

        offer = MODULE.calculate(data)["offers"][0]

        self.assertIn("negative_contribution", offer["flags"])
        self.assertIn("below_minimum_margin", offer["flags"])
        self.assertIn("capacity_heavy", offer["flags"])

    def test_zero_delivery_hours_do_not_invent_hour_economics(self) -> None:
        data = payload()
        data["offers"][0]["delivery_hours"] = scalar(0)

        offer = MODULE.calculate(data)["offers"][0]

        self.assertIsNone(offer["contribution_per_delivery_hour"])
        self.assertIn("zero_delivery_hours", offer["flags"])

    def test_unknown_core_input_keeps_offer_and_portfolio_indeterminate(self) -> None:
        data = payload()
        data["offers"][0]["revenue"] = money(None, "unknown")

        result = MODULE.calculate(data)

        self.assertEqual(result["offers"][0]["status"], "indeterminate")
        self.assertEqual(result["portfolio"]["status"], "indeterminate")
        self.assertNotIn("advisory", result["economic_order"])
        self.assertIn("offers[0].revenue", result["missing_inputs"])

    def test_strategic_fit_is_reported_separately_from_economic_order(self) -> None:
        data = payload()
        data["offers"][0]["strategic_fit"] = scalar(1, "reported")

        result = MODULE.calculate(data)

        self.assertIn("low_strategic_fit", result["offers"][0]["flags"])
        self.assertIn("economic metrics only", result["ranking_scope"])

    def test_rejects_duplicate_offers_bad_rates_and_currency_mismatch(self) -> None:
        data = payload()
        data["offers"][1]["name"] = "advisory"
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.calculate(data)

        data = payload()
        data["thresholds"]["minimum_margin_rate"] = 1.1
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            MODULE.calculate(data)

        data = payload()
        data["offers"][0]["revenue"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "currency"):
            MODULE.calculate(data)

    def test_rejects_unknown_encoded_as_zero_and_invalid_scores(self) -> None:
        data = payload()
        data["offers"][0]["delivery_hours"] = scalar(0, "unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            MODULE.calculate(data)

        data = payload()
        data["offers"][0]["strategic_fit"] = scalar(6)
        with self.assertRaisesRegex(ValueError, "between 0 and 5"):
            MODULE.calculate(data)

    def test_cli_emits_json_and_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.json"
            valid.write_text(json.dumps(payload()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(valid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["portfolio"]["total_contribution"], 1_000_000)

            invalid = Path(directory) / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            completed = subprocess.run([sys.executable, str(SCRIPT), str(invalid)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertTrue(completed.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
