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
    / "skills/grants/grant-application-readiness/scripts/score_application_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("score_application_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def scalar(value, evidence="official_current"):
    return {"value": value, "evidence": evidence}


def unknown_scalar():
    return {"value": None, "evidence": "unknown"}


def source():
    return {
        "authority": "中小企業庁",
        "document": "公募要領",
        "url": "https://example.go.jp/",
        "checked_on": "2026-08-22",
        "version": "1.2 / 2026-07-10",
    }


def section(identifier, requirement_type, weight, draft_state, evidence_backing, hours=6):
    return {
        "id": identifier,
        "label": f"{identifier} の記載",
        "requirement_type": requirement_type,
        "weight": scalar(weight),
        "draft_state": draft_state,
        "evidence_backing": evidence_backing,
        "official_criterion_reference": "公募要領 p.12 審査項目",
        "owner": "founder",
        "estimated_hours": scalar(hours, "estimated"),
    }


def preparation(identifier, kind, necessity, status, lead_days, depends_on=None, expires_on=None):
    return {
        "id": identifier,
        "label": f"{identifier} の準備",
        "kind": kind,
        "necessity": necessity,
        "status": status,
        "issuer": "external_authority",
        "lead_time_days": scalar(lead_days, "reported"),
        "expires_on": expires_on,
        "depends_on": depends_on or [],
        "estimated_hours": scalar(1, "estimated"),
    }


def sample_input():
    return {
        "as_of_date": "2026-08-22",
        "program": {
            "label": "ものづくり補助金",
            "round_label": "第3回",
            "requirements_source": source(),
        },
        "fit_assessment": {
            "decision": "進める",
            "gate_requirements": [
                {"id": "eligible-expenses", "status": "confirmed"},
                {"id": "company-size", "status": "confirmed"},
            ],
        },
        "submission_deadline": {"date": "2026-10-15", "time": "17:00", "evidence": "official_current"},
        "sections": [
            section("current-business", "required", 3, "draft", "reported", hours=6),
            section("investment-plan", "required", 5, "outline", "documented", hours=12),
            section("policy-fit", "optional", 2, "not_started", "unknown", hours=3),
        ],
        "scoring_items": [
            {
                "id": "wage-increase",
                "label": "賃上げ加点",
                "points": scalar(10),
                "status": "likely",
                "requires_certification": True,
                "certification_item_id": "wage-pledge",
                "post_award_obligation": "未達の場合は返還または加点取消の対象",
                "obligation_accepted": None,
            },
            {
                "id": "digital",
                "label": "デジタル加点",
                "points": scalar(5),
                "status": "confirmed",
                "requires_certification": False,
                "certification_item_id": None,
                "post_award_obligation": None,
                "obligation_accepted": None,
            },
            {
                "id": "green",
                "label": "グリーン加点",
                "points": scalar(6),
                "status": "unclear",
                "requires_certification": False,
                "certification_item_id": None,
                "post_award_obligation": None,
                "obligation_accepted": None,
            },
        ],
        "preparation_items": [
            preparation("gbizid", "account", "required", "requested", 14),
            preparation(
                "tax-certificate",
                "document",
                "required",
                "not_started",
                7,
                depends_on=["gbizid"],
                expires_on="2026-12-01",
            ),
            preparation(
                "expert-review", "review", "required", "not_started", 10, depends_on=["tax-certificate"]
            ),
            preparation("wage-pledge", "certification", "conditional", "not_started", 3),
        ],
        "available_hours_per_week": scalar(8, "reported"),
    }


def schedule_by_id(result):
    return {row["id"]: row for row in result["schedule"]["items"]}


class GrantApplicationReadinessTests(unittest.TestCase):
    def test_scores_sections_by_draft_state_and_evidence_backing(self):
        result = MODULE.calculate(sample_input())
        sections = result["sections"]
        scored = {item["id"]: item for item in sections["scored"]}

        self.assertEqual(scored["current-business"]["points"], Decimal("1.5"))
        self.assertEqual(scored["investment-plan"]["points"], Decimal("1.25"))
        self.assertEqual(sections["required_readiness_percent"], Decimal("34.4"))
        self.assertEqual(sections["all_sections_readiness_percent"], Decimal("27.5"))
        self.assertEqual(sections["confidence_percent"], Decimal("68.0"))
        self.assertEqual(result["days_to_deadline"], 54)

    def test_unknown_evidence_backing_zeroes_points_but_keeps_weight_in_confidence(self):
        data = sample_input()
        data["sections"][1]["evidence_backing"] = "unknown"
        result = MODULE.calculate(data)
        scored = {item["id"]: item for item in result["sections"]["scored"]}

        self.assertEqual(scored["investment-plan"]["points"], 0)
        self.assertEqual(scored["investment-plan"]["max_points"], 5)
        self.assertEqual(result["sections"]["confidence_percent"], Decimal("18.0"))
        self.assertIn("sections[1].evidence_backing", result["missing_inputs"])
        self.assertEqual(result["readiness_status"], "indeterminate")

    def test_polished_section_without_evidence_is_flagged(self):
        data = sample_input()
        data["sections"][0]["draft_state"] = "final"
        data["sections"][0]["evidence_backing"] = "unknown"
        result = MODULE.calculate(data)

        self.assertEqual(result["sections"]["unsupported_final_sections"], ["current-business"])
        scored = {item["id"]: item for item in result["sections"]["scored"]}
        self.assertEqual(scored["current-business"]["points"], 0)
        self.assertIn(
            {
                "id": "current-business",
                "area": "section",
                "severity": "high",
                "reason": "polished_without_evidence",
                "latest_start_date": None,
            },
            result["gaps"],
        )

    def test_buckets_scoring_points_without_summing_across_statuses(self):
        scoring = MODULE.calculate(sample_input())["scoring"]

        self.assertEqual(scoring["claimable_points"], 5)
        self.assertEqual(scoring["contingent_points"], 10)
        self.assertEqual(scoring["unresolved_points"], 6)
        self.assertEqual(scoring["forgone_points"], 0)
        self.assertEqual(scoring["total_available_points"], 21)
        self.assertNotIn("expected_points", scoring)
        self.assertNotIn("certification_references", scoring)

    def test_flags_unaccepted_post_award_obligation(self):
        result = MODULE.calculate(sample_input())
        self.assertEqual(
            result["scoring"]["items_with_unaccepted_obligations"],
            [{"id": "wage-increase", "post_award_obligation": "未達の場合は返還または加点取消の対象"}],
        )

        with self.subTest("accepting the obligation clears the gap"):
            data = sample_input()
            data["scoring_items"][0]["obligation_accepted"] = True
            cleared = MODULE.calculate(data)
            self.assertEqual(cleared["scoring"]["items_with_unaccepted_obligations"], [])

    def test_back_schedules_dependency_chain_and_reports_critical_path(self):
        result = MODULE.calculate(sample_input())
        rows = schedule_by_id(result)

        self.assertEqual(rows["gbizid"]["downstream_lead_days"], 17)
        self.assertEqual(rows["gbizid"]["latest_start_date"], "2026-09-14")
        self.assertEqual(rows["gbizid"]["slack_days"], 23)
        self.assertEqual(rows["tax-certificate"]["latest_start_date"], "2026-09-28")
        self.assertEqual(rows["expert-review"]["latest_start_date"], "2026-10-05")
        self.assertEqual(
            result["schedule"]["critical_path"], ["gbizid", "tax-certificate", "expert-review"]
        )
        self.assertEqual(result["schedule"]["minimum_slack_days"], 23)
        self.assertEqual(result["schedule"]["late_items"], [])
        self.assertEqual(result["readiness_status"], "gaps_with_time")

    def test_held_item_contributes_no_lead_time(self):
        data = sample_input()
        data["preparation_items"][0]["status"] = "held"
        rows = schedule_by_id(MODULE.calculate(data))

        self.assertEqual(rows["gbizid"]["effective_lead_days"], 0)
        self.assertEqual(rows["gbizid"]["latest_start_date"], "2026-09-28")

    def test_negative_slack_on_required_item_yields_blocked(self):
        data = sample_input()
        data["preparation_items"][0]["lead_time_days"] = scalar(60, "reported")
        result = MODULE.calculate(data)

        self.assertLess(result["schedule"]["minimum_slack_days"], 0)
        self.assertEqual(result["schedule"]["late_items"], ["gbizid"])
        self.assertEqual(result["readiness_status"], "blocked")

    def test_expiring_certificate_before_deadline_is_blocking(self):
        data = sample_input()
        data["preparation_items"][1]["status"] = "held"
        data["preparation_items"][1]["expires_on"] = "2026-09-30"
        result = MODULE.calculate(data)

        self.assertEqual(result["preparation"]["expiring_before_submission"], ["tax-certificate"])
        self.assertEqual(result["readiness_status"], "blocked")

    def test_effort_shortfall_yields_gaps_without_time(self):
        data = sample_input()
        data["available_hours_per_week"] = scalar(1, "reported")
        result = MODULE.calculate(data)

        self.assertEqual(result["effort"]["total_estimated_hours"], 25)
        self.assertEqual(result["effort"]["weeks_to_deadline"], Decimal("7.71"))
        self.assertEqual(result["effort"]["available_hours"], Decimal("7.71"))
        self.assertEqual(result["effort"]["hours_shortfall"], Decimal("17.29"))
        self.assertEqual(result["readiness_status"], "gaps_without_time")

        with self.subTest("unknown weekly hours records a reason instead"):
            unknown = sample_input()
            unknown["available_hours_per_week"] = unknown_scalar()
            outcome = MODULE.calculate(unknown)
            self.assertIsNone(outcome["effort"]["available_hours"])
            self.assertIsNone(outcome["effort"]["hours_shortfall"])
            self.assertIn("available_hours_per_week", outcome["missing_inputs"])
            self.assertTrue(
                any("available_hours_per_week" in reason for reason in outcome["status_reasons"])
            )

    def test_readiness_status_precedence(self):
        cases = {
            "indeterminate": (
                lambda data: data["preparation_items"][0].update({"status": "unknown"}),
                "indeterminate",
            ),
            "blocked by an ineligible gate": (
                lambda data: data["fit_assessment"]["gate_requirements"].append(
                    {"id": "expense-category", "status": "ineligible"}
                ),
                "blocked",
            ),
            "blocked by an upstream decision": (
                lambda data: data["fit_assessment"].update({"decision": "見送る"}),
                "blocked",
            ),
            "gaps without time": (
                lambda data: data.update({"available_hours_per_week": scalar(1, "reported")}),
                "gaps_without_time",
            ),
            "gaps with time": (lambda data: None, "gaps_with_time"),
            "submission path clear": (
                lambda data: (
                    data["preparation_items"].__setitem__(
                        0, preparation("gbizid", "account", "required", "held", 14)
                    ),
                    data["preparation_items"].__setitem__(
                        1,
                        preparation(
                            "tax-certificate",
                            "document",
                            "required",
                            "held",
                            7,
                            depends_on=["gbizid"],
                            expires_on="2026-12-01",
                        ),
                    ),
                    data["preparation_items"].__setitem__(
                        2,
                        preparation(
                            "expert-review",
                            "review",
                            "required",
                            "held",
                            10,
                            depends_on=["tax-certificate"],
                        ),
                    ),
                    data["preparation_items"].__setitem__(
                        3, preparation("wage-pledge", "certification", "conditional", "held", 3)
                    ),
                    data["scoring_items"][0].__setitem__("obligation_accepted", True),
                    data["sections"].__setitem__(
                        2, section("policy-fit", "optional", 2, "not_started", "estimated", hours=3)
                    ),
                ),
                "submission_path_clear",
            ),
        }
        for name, (mutate, expected) in cases.items():
            with self.subTest(name):
                data = sample_input()
                mutate(data)
                self.assertEqual(MODULE.calculate(data)["readiness_status"], expected)

    def test_unclear_gate_requirement_is_reported_without_re_evaluating_eligibility(self):
        data = sample_input()
        data["fit_assessment"]["decision"] = "追加確認"
        data["fit_assessment"]["gate_requirements"][1]["status"] = "unclear"
        result = MODULE.calculate(data)

        self.assertEqual(result["fit_assessment"]["unclear_gate_requirements"], ["company-size"])
        self.assertTrue(
            any("grant-subsidy-fit" in reason for reason in result["status_reasons"])
        )

    def test_rejects_dependency_cycle_and_unknown_dependency(self):
        with self.subTest("cycle"):
            data = sample_input()
            data["preparation_items"][0]["depends_on"] = ["expert-review"]
            with self.assertRaisesRegex(ValueError, "dependency cycle detected"):
                MODULE.calculate(data)

        with self.subTest("unknown dependency"):
            data = sample_input()
            data["preparation_items"][0]["depends_on"] = ["missing-item"]
            with self.assertRaisesRegex(ValueError, "references an unknown preparation item"):
                MODULE.calculate(data)

    def test_rejects_past_deadline_duplicate_ids_and_invalid_enums(self):
        cases = {
            "deadline already passed": (
                lambda data: data["submission_deadline"].update({"date": "2026-08-21"}),
                "must not precede as_of_date",
            ),
            "malformed deadline time": (
                lambda data: data["submission_deadline"].update({"time": "5pm"}),
                "must be an HH:MM time",
            ),
            "identifier reused across collections": (
                lambda data: data["preparation_items"][0].update({"id": "current-business"}),
                "duplicates an earlier identifier",
            ),
            "non positive weight": (
                lambda data: data["sections"][0].update({"weight": scalar(0)}),
                "weight.value must be positive",
            ),
            "negative points": (
                lambda data: data["scoring_items"][0].update({"points": scalar(-1)}),
                "points.value must be nonnegative",
            ),
            "required item marked not applicable": (
                lambda data: data["preparation_items"][0].update({"status": "not_applicable"}),
                "a required preparation item cannot be not_applicable",
            ),
            "certification without a certification item": (
                lambda data: data["scoring_items"][0].update({"certification_item_id": "gbizid"}),
                "must reference a preparation item of kind certification",
            ),
            "certification item on a non certified score": (
                lambda data: data["scoring_items"][1].update({"certification_item_id": "wage-pledge"}),
                "only allowed when requires_certification is true",
            ),
            "requirements checked after the as_of date": (
                lambda data: data["program"]["requirements_source"].update(
                    {"checked_on": "2026-08-23"}
                ),
                "checked_on must not be after as_of_date",
            ),
            "negative lead time": (
                lambda data: data["preparation_items"][0].update(
                    {"lead_time_days": scalar(-1, "reported")}
                ),
                "lead_time_days.value must be nonnegative",
            ),
            "fractional lead time": (
                lambda data: data["preparation_items"][0].update(
                    {"lead_time_days": scalar(1.5, "reported")}
                ),
                "whole number of days",
            ),
            "non positive weekly hours": (
                lambda data: data.update({"available_hours_per_week": scalar(0, "reported")}),
                "must be positive",
            ),
            "unknown draft state": (
                lambda data: data["sections"][0].update({"draft_state": "polished"}),
                "draft_state must be one of",
            ),
            "unknown requirement status": (
                lambda data: data["fit_assessment"]["gate_requirements"][0].update(
                    {"status": "probably"}
                ),
                "status must be one of",
            ),
            "unknown value carrying a number": (
                lambda data: data["sections"][0].update(
                    {"weight": {"value": 3, "evidence": "unknown"}}
                ),
                "unknown value must be null",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name):
                data = sample_input()
                mutate(data)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.calculate(data)

    def test_missing_certification_item_is_reported(self):
        data = sample_input()
        data["scoring_items"][0]["certification_item_id"] = None
        result = MODULE.calculate(data)

        self.assertEqual(result["scoring"]["items_missing_certification_item"], ["wage-increase"])
        self.assertIn(
            {
                "id": "wage-increase",
                "area": "scoring",
                "severity": "medium",
                "reason": "certification_item_not_identified",
                "latest_start_date": None,
            },
            result["gaps"],
        )

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
        self.assertEqual(json.loads(valid.stdout)["days_to_deadline"], 54)
        self.assertEqual(valid.stderr, "")
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed.stdout, "")
        self.assertIn("input error:", malformed.stderr)
        self.assertEqual(invalid_contract.returncode, 2)
        self.assertIn("input must be an object", invalid_contract.stderr)
        self.assertEqual(missing_argument.returncode, 2)
        self.assertIn("usage: score_application_readiness.py", missing_argument.stderr)


if __name__ == "__main__":
    unittest.main()
