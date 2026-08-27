import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "skills/grants/grant-execution-and-reporting/scripts/plan_grant_execution.py"
)
SPEC = importlib.util.spec_from_file_location("plan_grant_execution", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

CASH_MONTHS = [f"2026-{month:02d}" for month in range(8, 13)] + [
    f"2027-{month:02d}" for month in range(1, 7)
]


def money(amount, evidence="confirmed"):
    return {"amount": amount, "evidence": evidence}


def scalar(value, evidence="official_current"):
    return {"value": value, "evidence": evidence}


def unknown_money():
    return {"amount": None, "evidence": "unknown"}


def source():
    return {
        "authority": "中小企業庁",
        "document": "交付要綱",
        "url": "https://example.go.jp/",
        "checked_on": "2026-08-22",
        "version": "2026年度版",
    }


def evidence_item(kind, necessity, status):
    return {"kind": kind, "necessity": necessity, "status": status}


def cost_item(identifier, category, approved, committed, payment_date, eligibility, **overrides):
    entry = {
        "id": identifier,
        "label": f"{identifier} の経費",
        "category": category,
        "approved_amount": money(approved, "official_current"),
        "committed_amount": money(committed),
        "planned_payment_date": payment_date,
        "eligibility_status": eligibility,
        "ordered_before_approval": False,
        "quotes_required": scalar(2),
        "quotes_obtained": scalar(2, "reported"),
        "paid_by": "bank_transfer",
        "evidence_items": [evidence_item("quote", "required", "held")],
    }
    entry.update(overrides)
    return entry


def sample_input():
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "grant": {
            "label": "ものづくり補助金 第3回",
            "decision_date": "2026-07-01",
            "approved_total_eligible_cost": money(8000000, "official_current"),
            "subsidy_rate": scalar(0.5),
            "subsidy_cap": money(4000000, "official_current"),
            "project_start_date": "2026-07-01",
            "project_end_date": "2027-02-28",
            "report_due_date": "2027-03-31",
            "expected_payment_date": {"date": "2027-06-30", "evidence": "estimated"},
            "interim_payment_available": False,
            "requirements_source": source(),
        },
        "cost_items": [
            cost_item(
                "machine-a",
                "machinery",
                3000000,
                3200000,
                "2026-11-30",
                "confirmed",
                evidence_items=[
                    evidence_item("quote", "required", "held"),
                    evidence_item("invoice", "required", "pending"),
                ],
            ),
            cost_item(
                "system-b",
                "system",
                2000000,
                2000000,
                "2027-01-31",
                "likely",
                quotes_obtained=scalar(1, "reported"),
                evidence_items=[evidence_item("quote", "required", "missing")],
            ),
            cost_item(
                "ad-c",
                "advertising",
                1000000,
                900000,
                "2026-09-30",
                "unclear",
                ordered_before_approval=True,
                paid_by="cash",
                evidence_items=[evidence_item("invoice", "required", "held")],
            ),
        ],
        "cash": {
            "available_cash": money(3000000),
            "minimum_cash_buffer": money(1000000, "reported"),
            "monthly_net_cash_before_grant": [
                {"month": month, "amount": money(200000, "reported")} for month in CASH_MONTHS
            ],
        },
        "financing_options": [
            {
                "id": "tsunagi",
                "label": "つなぎ融資",
                "available_amount": money(3000000, "reported"),
                "lead_time_days": scalar(30, "reported"),
                "status": "reported",
            },
            {
                "id": "card",
                "label": "法人カード枠",
                "available_amount": money(500000, "reported"),
                "lead_time_days": scalar(5, "reported"),
                "status": "reported",
            },
        ],
    }


def findings_by_rule(result):
    return {finding["rule"]: finding for finding in result["risk_findings"]}


class GrantExecutionTests(unittest.TestCase):
    def test_calculates_three_separate_subsidy_figures(self):
        estimate = MODULE.calculate(sample_input())["subsidy_estimate"]

        self.assertEqual(estimate["eligible_base_confirmed"], 3000000)
        self.assertEqual(estimate["eligible_base_confirmed_plus_likely"], 5000000)
        self.assertEqual(estimate["eligible_base_including_unclear"], 5900000)
        self.assertEqual(estimate["subsidy_confirmed_only"], 1500000)
        self.assertEqual(estimate["subsidy_confirmed_plus_likely"], 2500000)
        self.assertEqual(estimate["subsidy_including_unclear"], 2950000)
        self.assertEqual(
            estimate["cap_binding"],
            {"confirmed_only": False, "confirmed_plus_likely": False, "including_unclear": False},
        )

    def test_cap_binds_when_the_calculated_subsidy_exceeds_it(self):
        data = sample_input()
        data["grant"]["subsidy_cap"] = money(2000000, "official_current")
        estimate = MODULE.calculate(data)["subsidy_estimate"]

        self.assertEqual(estimate["subsidy_confirmed_only"], 1500000)
        self.assertIs(estimate["cap_binding"]["confirmed_only"], False)
        self.assertEqual(estimate["subsidy_confirmed_plus_likely"], 2000000)
        self.assertIs(estimate["cap_binding"]["confirmed_plus_likely"], True)

    def test_committed_over_approved_becomes_self_funded_overage(self):
        result = MODULE.calculate(sample_input())
        items = {item["id"]: item for item in result["cost_items"]}

        self.assertEqual(items["machine-a"]["eligible_amount"], 3000000)
        self.assertEqual(items["machine-a"]["overage"], 200000)
        self.assertEqual(items["machine-a"]["subsidy_contribution"], 1500000)
        self.assertEqual(result["subsidy_estimate"]["self_funded_overage"], 200000)
        self.assertEqual(result["subsidy_estimate"]["approved_vs_committed_delta"], 100000)

    def test_risk_findings_map_rules_to_severities(self):
        findings = findings_by_rule(MODULE.calculate(sample_input()))

        expected = {
            "ordered_before_approval": ("high", "ad-c", 450000),
            "eligibility_unclear": ("medium", "ad-c", 450000),
            "quote_shortfall": ("medium", "system-b", 1000000),
            "missing_required_evidence": ("medium", "system-b", 1000000),
            "cash_payment": ("low", "ad-c", 450000),
            "pending_required_evidence": ("low", "machine-a", 1500000),
        }
        for rule, (severity, item_id, at_risk) in expected.items():
            with self.subTest(rule):
                self.assertEqual(findings[rule]["severity"], severity)
                self.assertEqual(findings[rule]["item_id"], item_id)
                self.assertEqual(findings[rule]["amount_at_risk"], at_risk)
                self.assertTrue(findings[rule]["detail"])

        with self.subTest("ineligible expense"):
            data = sample_input()
            data["cost_items"][1]["eligibility_status"] = "ineligible"
            outcome = MODULE.calculate(data)
            self.assertEqual(findings_by_rule(outcome)["eligibility_ineligible"]["severity"], "high")
            self.assertEqual(
                {item["id"]: item["status"] for item in outcome["cost_items"]}["system-b"], "excluded"
            )
            self.assertEqual(outcome["subsidy_estimate"]["subsidy_confirmed_plus_likely"], 1500000)

        with self.subTest("unknown quote requirement is never defaulted"):
            data = sample_input()
            data["cost_items"][0]["quotes_required"] = {"value": None, "evidence": "unknown"}
            outcome = MODULE.calculate(data)
            self.assertEqual(findings_by_rule(outcome)["quotes_required_unknown"]["severity"], "medium")
            self.assertIn("cost_items[0].quotes_required", outcome["missing_inputs"])

    def test_clawback_exposure_deduplicates_item_at_max_severity(self):
        exposure = MODULE.calculate(sample_input())["clawback_exposure"]

        self.assertEqual(exposure["items_at_risk"], ["ad-c", "machine-a", "system-b"])
        self.assertEqual(
            exposure["by_severity"],
            {"high": Decimal("450000"), "medium": Decimal("1000000"), "low": Decimal("1500000")},
        )
        self.assertEqual(exposure["total_amount_at_risk"], 2950000)

    def test_payment_after_project_period_is_high_finding_not_rejection(self):
        data = sample_input()
        data["cost_items"][1]["planned_payment_date"] = "2027-03-15"
        data["cash"]["monthly_net_cash_before_grant"] = [
            {"month": month, "amount": money(200000, "reported")} for month in CASH_MONTHS
        ]
        findings = findings_by_rule(MODULE.calculate(data))

        self.assertEqual(findings["payment_after_project_period"]["severity"], "high")
        self.assertEqual(findings["payment_after_project_period"]["item_id"], "system-b")

    def test_bridge_need_and_arrangement_date_with_known_payment_date(self):
        result = MODULE.calculate(sample_input())
        path = result["cash_path"]

        self.assertIs(path["subsidy_inflow_modeled"], True)
        self.assertEqual(path["lowest_cash"], {"month": "2027-01", "amount": Decimal("-1900000")})
        self.assertEqual(path["bridge_financing_need"], 2900000)
        self.assertEqual(path["bridge_needed_from_month"], "2026-11")
        self.assertEqual(path["bridge_needed_from_date"], "2026-11-30")
        self.assertEqual(path["carry_days"], 150)
        options = {option["id"]: option for option in result["financing_options"]}
        self.assertIs(options["tsunagi"]["sufficient"], True)
        self.assertEqual(options["tsunagi"]["arrange_by_date"], "2026-10-31")
        self.assertIs(options["card"]["sufficient"], False)
        self.assertEqual(options["card"]["shortfall"], 2400000)
        self.assertEqual(result["latest_arrangement_date"], "2026-10-31")

    def test_unknown_payment_date_models_no_inflow(self):
        data = sample_input()
        data["grant"]["expected_payment_date"] = {"date": None, "evidence": "unknown"}
        data["cash"]["monthly_net_cash_before_grant"] = [
            {"month": month, "amount": money(200000, "reported")}
            for month in [f"2026-{month:02d}" for month in range(8, 13)] + ["2027-01"]
        ]
        result = MODULE.calculate(data)
        path = result["cash_path"]

        self.assertIs(path["subsidy_inflow_modeled"], False)
        self.assertIsNone(path["carry_days"])
        self.assertTrue(all(month["subsidy_inflow"] == 0 for month in path["months"]))
        self.assertEqual(path["bridge_financing_need"], 2900000)
        self.assertIn("grant.expected_payment_date", result["missing_inputs"])
        self.assertEqual(result["status"], "indeterminate")

    def test_financing_option_shortfall_leaves_latest_arrangement_date_null(self):
        data = sample_input()
        data["financing_options"] = [data["financing_options"][1]]
        result = MODULE.calculate(data)

        self.assertIsNone(result["latest_arrangement_date"])
        self.assertEqual(result["financing_options"][0]["shortfall"], 2400000)

    def test_unknown_committed_amount_excludes_item_and_marks_indeterminate(self):
        data = sample_input()
        data["cost_items"][0]["committed_amount"] = unknown_money()
        result = MODULE.calculate(data)
        items = {item["id"]: item for item in result["cost_items"]}

        self.assertEqual(items["machine-a"]["status"], "indeterminate")
        self.assertIsNone(items["machine-a"]["eligible_amount"])
        self.assertIsNone(result["subsidy_estimate"]["eligible_base_confirmed"])
        self.assertIsNone(result["subsidy_estimate"]["subsidy_confirmed_only"])
        self.assertIsNone(result["subsidy_estimate"]["self_funded_overage"])
        self.assertIs(result["cash_path"]["determinate"], False)
        self.assertIsNone(result["cash_path"]["bridge_financing_need"])
        self.assertIn("cost_items[0].committed_amount", result["missing_inputs"])
        self.assertEqual(result["status"], "indeterminate")

    def test_evidence_gaps_list_required_items_not_held(self):
        gaps = MODULE.calculate(sample_input())["evidence_gaps"]

        self.assertIn(
            {"item_id": "machine-a", "kind": "invoice", "necessity": "required", "status": "pending"},
            gaps,
        )
        self.assertIn(
            {"item_id": "system-b", "kind": "quote", "necessity": "required", "status": "missing"},
            gaps,
        )

    def test_rejects_inconsistent_grant_envelope(self):
        cases = {
            "subsidy rate above one": (
                lambda data: data["grant"].update({"subsidy_rate": scalar(1.5)}),
                "greater than 0 and at most 1",
            ),
            "subsidy rate of zero": (
                lambda data: data["grant"].update({"subsidy_rate": scalar(0)}),
                "greater than 0 and at most 1",
            ),
            "approved amounts above the envelope": (
                lambda data: data["cost_items"][0].update(
                    {"approved_amount": money(6000000, "official_current")}
                ),
                "exceed grant.approved_total_eligible_cost",
            ),
            "report due before the project ends": (
                lambda data: data["grant"].update({"report_due_date": "2027-01-31"}),
                "report_due_date must not precede project_end_date",
            ),
            "project ending before it starts": (
                lambda data: data["grant"].update({"project_end_date": "2026-06-30"}),
                "project_end_date must not precede project_start_date",
            ),
            "payment before the project ends without an interim payment": (
                lambda data: data["grant"].update(
                    {"expected_payment_date": {"date": "2026-12-31", "evidence": "estimated"}}
                ),
                "cannot precede project_end_date without an interim payment",
            ),
            "unknown payment date carrying a value": (
                lambda data: data["grant"].update(
                    {"expected_payment_date": {"date": "2027-06-30", "evidence": "unknown"}}
                ),
                "unknown date must be null",
            ),
            "payment before the decision date without the flag": (
                lambda data: data["cost_items"][0].update({"planned_payment_date": "2026-06-01"}),
                "not marked ordered_before_approval",
            ),
            "duplicate cost item id": (
                lambda data: data["cost_items"].append(copy.deepcopy(data["cost_items"][0])),
                "duplicates an earlier cost item",
            ),
            "duplicate financing option id": (
                lambda data: data["financing_options"].append(
                    copy.deepcopy(data["financing_options"][0])
                ),
                "duplicates an earlier financing option",
            ),
            "short monthly series": (
                lambda data: data["cash"]["monthly_net_cash_before_grant"].pop(),
                "must cover through 2027-06",
            ),
            "non contiguous monthly series": (
                lambda data: data["cash"]["monthly_net_cash_before_grant"][3].update(
                    {"month": "2026-12"}
                ),
                "month must be 2026-11",
            ),
            "unknown cost category": (
                lambda data: data["cost_items"][0].update({"category": "rent"}),
                "category must be one of",
            ),
            "unknown evidence status": (
                lambda data: data["cost_items"][0]["evidence_items"][0].update({"status": "maybe"}),
                "status must be one of",
            ),
            "negative quote count": (
                lambda data: data["cost_items"][0].update({"quotes_obtained": scalar(-1, "reported")}),
                "must be nonnegative",
            ),
            "requirements checked after the as_of date": (
                lambda data: data["grant"]["requirements_source"].update(
                    {"checked_on": "2026-08-23"}
                ),
                "checked_on must not be after as_of_date",
            ),
            "malformed currency": (
                lambda data: data.update({"currency": "jpy"}),
                "three-letter uppercase code",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name):
                data = sample_input()
                mutate(data)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.calculate(data)

    def test_cli_returns_json_for_valid_input_and_error_for_invalid_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            valid_path = temporary_path / "valid.json"
            invalid_path = temporary_path / "invalid.json"
            invalid_contract_path = temporary_path / "invalid-contract.json"
            valid_path.write_text(json.dumps(sample_input()), encoding="utf-8")
            invalid_path.write_text("{", encoding="utf-8")
            invalid_contract_path.write_text("[]", encoding="utf-8")

            valid = subprocess.run(
                [sys.executable, str(SCRIPT), str(valid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            malformed = subprocess.run(
                [sys.executable, str(SCRIPT), str(invalid_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            invalid_contract = subprocess.run(
                [sys.executable, str(SCRIPT), str(invalid_contract_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            missing_argument = subprocess.run(
                [sys.executable, str(SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(valid.returncode, 0)
        self.assertEqual(json.loads(valid.stdout)["as_of_date"], "2026-08-22")
        self.assertEqual(valid.stderr, "")
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed.stdout, "")
        self.assertIn("input error:", malformed.stderr)
        self.assertEqual(invalid_contract.returncode, 2)
        self.assertIn("input must be an object", invalid_contract.stderr)
        self.assertEqual(missing_argument.returncode, 2)
        self.assertIn("usage: plan_grant_execution.py", missing_argument.stderr)


if __name__ == "__main__":
    unittest.main()
