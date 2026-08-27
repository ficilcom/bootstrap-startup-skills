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
    / "skills/management/monthly-budget-variance-review/scripts/analyze_budget_variance.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_budget_variance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount, evidence="confirmed"):
    return {"amount": amount, "evidence": evidence}


def scalar(value, evidence="confirmed"):
    return {"value": value, "evidence": evidence}


def triage(**stages):
    base = {stage: "not_checked" for stage in MODULE.STAGE_ORDER}
    base.update(stages)
    return base


def segment(identifier, budget_units, actual_units, budget_price, actual_price):
    return {
        "id": identifier,
        "budget_units": scalar(budget_units),
        "actual_units": scalar(actual_units),
        "budget_unit_price": money(budget_price),
        "actual_unit_price": money(actual_price, "reported"),
    }


def sample_input():
    return {
        "as_of_date": "2026-09-05",
        "currency": "JPY",
        "period": {
            "label": "2026-08",
            "start": "2026-08-01",
            "end": "2026-08-31",
            "close_state": "preliminary",
        },
        "comparison_basis": "budget",
        "materiality_policy": {
            "absolute": money(100000, "reported"),
            "relative_percent": scalar(10, "reported"),
            "rule": "either",
        },
        "lines": [
            {
                "id": "revenue-saas",
                "label": "SaaS売上",
                "statement_section": "revenue",
                "direction_favorable": "higher",
                "budget": money(3000000),
                "actual": money(2600000, "reported"),
                "triage": triage(
                    data_quality="cleared",
                    definition_change="cleared",
                    timing="cleared",
                    mix="cleared",
                    real_change="explains",
                ),
                "explanation": "新規獲得の減少が継続",
                "explanation_evidence": "reported",
            },
            {
                "id": "cogs-hosting",
                "label": "ホスティング原価",
                "statement_section": "cogs",
                "direction_favorable": "lower",
                "budget": money(400000),
                "actual": money(520000, "reported"),
                "triage": triage(
                    data_quality="cleared", definition_change="cleared", timing="explains"
                ),
                "explanation": "8月末請求が9月計上へ",
                "explanation_evidence": "confirmed",
            },
            {
                "id": "opex-tools",
                "label": "ツール費",
                "statement_section": "opex",
                "direction_favorable": "lower",
                "budget": money(200000),
                "actual": money(205000, "reported"),
                "triage": triage(),
                "explanation": None,
                "explanation_evidence": "unknown",
            },
        ],
        "volume_price_lines": [
            {
                "id": "revenue-saas",
                "segments": [
                    segment("smb", 100, 90, 10000, 9500),
                    segment("mid", 100, 80, 20000, 20000),
                ],
            }
        ],
        "structural_candidates": ["revenue-saas"],
    }


def lines_by_id(result):
    return {line["id"]: line for line in result["lines"]}


class MonthlyBudgetVarianceTests(unittest.TestCase):
    def test_calculates_variance_materiality_and_favorability(self):
        result = MODULE.calculate(sample_input())
        lines = lines_by_id(result)

        self.assertEqual(lines["revenue-saas"]["variance"], -400000)
        self.assertEqual(lines["revenue-saas"]["variance_percent"], Decimal("-13.333333"))
        self.assertIs(lines["revenue-saas"]["favorable"], False)
        self.assertIs(lines["revenue-saas"]["material"], True)
        self.assertEqual(lines["revenue-saas"]["materiality_source"], "policy")
        self.assertIs(lines["cogs-hosting"]["favorable"], False)
        self.assertIs(lines["opex-tools"]["material"], False)
        self.assertEqual(lines["opex-tools"]["attribution"], "not_triaged")
        self.assertIs(result["provisional"], True)
        self.assertEqual(result["totals"]["material_line_count"], 2)
        self.assertEqual(result["totals"]["net_profit_variance"], -525000)
        self.assertEqual(
            result["totals"]["gross_profit"],
            {"budget": Decimal("2600000"), "actual": Decimal("2080000"), "variance": Decimal("-520000")},
        )

    def test_line_threshold_overrides_the_policy(self):
        data = sample_input()
        data["lines"][2]["materiality_threshold"] = money(1000, "reported")
        lines = lines_by_id(MODULE.calculate(data))

        self.assertIs(lines["opex-tools"]["material"], True)
        self.assertEqual(lines["opex-tools"]["materiality_source"], "line_threshold")

    def test_zero_budget_line_reports_null_percent_with_reason(self):
        data = sample_input()
        data["lines"][2]["budget"] = money(0)
        lines = lines_by_id(MODULE.calculate(data))

        self.assertIsNone(lines["opex-tools"]["variance_percent"])
        self.assertEqual(lines["opex-tools"]["variance_percent_reason"], "zero_budget")
        self.assertIs(lines["opex-tools"]["material"], True)
        self.assertEqual(lines["opex-tools"]["materiality_source"], "zero_budget")

    def test_triage_attributes_first_explaining_stage(self):
        lines = lines_by_id(MODULE.calculate(sample_input()))

        self.assertEqual(lines["revenue-saas"]["attribution"], "real_change")
        self.assertIsNone(lines["revenue-saas"]["blocking_stage"])
        self.assertEqual(lines["cogs-hosting"]["attribution"], "timing")
        self.assertEqual(lines["cogs-hosting"]["blocking_stage"], "mix")

    def test_later_stage_cannot_explain_over_an_open_earlier_stage(self):
        data = sample_input()
        data["lines"][0]["triage"] = triage(data_quality="unresolved", real_change="explains")
        result = MODULE.calculate(data)
        lines = lines_by_id(result)

        self.assertEqual(lines["revenue-saas"]["attribution"], "premature")
        self.assertEqual(lines["revenue-saas"]["blocking_stage"], "data_quality")
        self.assertEqual(
            result["triage_violations"],
            [
                {
                    "line_id": "revenue-saas",
                    "claimed_stage": "real_change",
                    "blocking_stage": "data_quality",
                }
            ],
        )
        self.assertEqual(result["structural_findings"], [])

    def test_all_stages_not_checked_yields_not_triaged_without_violation(self):
        data = sample_input()
        data["lines"][0]["triage"] = triage()
        result = MODULE.calculate(data)

        self.assertEqual(lines_by_id(result)["revenue-saas"]["attribution"], "not_triaged")
        self.assertEqual(result["triage_violations"], [])
        self.assertEqual(result["review_status"], "unexplained")

    def test_all_stages_cleared_without_an_explanation_is_unresolved(self):
        data = sample_input()
        data["lines"][0]["triage"] = triage(
            data_quality="cleared",
            definition_change="cleared",
            timing="cleared",
            mix="cleared",
            real_change="cleared",
        )
        lines = lines_by_id(MODULE.calculate(data))

        self.assertEqual(lines["revenue-saas"]["attribution"], "unresolved")
        self.assertIsNone(lines["revenue-saas"]["blocking_stage"])

    def test_price_volume_mix_decomposition_reconciles(self):
        decomposition = lines_by_id(MODULE.calculate(sample_input()))["revenue-saas"]["decomposition"]

        self.assertEqual(decomposition["total_variance"], -545000)
        self.assertEqual(decomposition["price_effect"], -45000)
        self.assertEqual(decomposition["volume_effect"], -450000)
        self.assertEqual(decomposition["mix_effect"], -50000)
        self.assertEqual(decomposition["mix_method"], "derived_residual")
        self.assertEqual(
            decomposition["price_effect"]
            + decomposition["volume_effect"]
            + decomposition["mix_effect"],
            decomposition["total_variance"],
        )

    def test_zero_budget_units_disables_decomposition(self):
        data = sample_input()
        data["lines"][0]["budget"] = money(0)
        data["volume_price_lines"][0]["segments"] = [segment("smb", 0, 90, 10000, 9500)]
        decomposition = lines_by_id(MODULE.calculate(data))["revenue-saas"]["decomposition"]

        self.assertEqual(decomposition["reason"], "zero_budget_units")
        self.assertIsNone(decomposition["price_effect"])
        self.assertIsNone(decomposition["volume_effect"])
        self.assertIsNone(decomposition["mix_effect"])

    def test_partial_segment_coverage_is_flagged_not_rejected(self):
        decomposition = lines_by_id(MODULE.calculate(sample_input()))["revenue-saas"]["decomposition"]

        self.assertIs(decomposition["partial_coverage"], True)
        self.assertEqual(decomposition["segment_coverage_delta"], 0)
        self.assertEqual(decomposition["segment_actual_coverage_delta"], 145000)

        with self.subTest("segment budget above the line budget is rejected"):
            data = sample_input()
            data["volume_price_lines"][0]["segments"].append(segment("ent", 10, 10, 100000, 100000))
            with self.assertRaisesRegex(ValueError, "segment budget total cannot exceed"):
                MODULE.calculate(data)

    def test_review_status_precedence(self):
        with self.subTest("indeterminate"):
            data = sample_input()
            data["lines"][0]["actual"] = {"amount": None, "evidence": "unknown"}
            result = MODULE.calculate(data)
            self.assertEqual(result["review_status"], "indeterminate")
            self.assertIsNone(result["lines"][0]["material"])
            self.assertEqual(result["lines"][0]["materiality_source"], "indeterminate")
            self.assertIn("lines[0].actual", result["missing_inputs"])

        with self.subTest("unexplained"):
            data = sample_input()
            data["lines"][0]["triage"] = triage(data_quality="unresolved")
            self.assertEqual(MODULE.calculate(data)["review_status"], "unexplained")

        with self.subTest("partially explained"):
            data = sample_input()
            data["lines"][1]["triage"] = triage(data_quality="unresolved")
            self.assertEqual(MODULE.calculate(data)["review_status"], "partially_explained")

        with self.subTest("explained"):
            data = sample_input()
            result = MODULE.calculate(data)
            self.assertEqual(result["review_status"], "explained")
            self.assertIs(result["provisional"], True)

        with self.subTest("final close is not provisional"):
            data = sample_input()
            data["period"]["close_state"] = "final"
            self.assertIs(MODULE.calculate(data)["provisional"], False)

    def test_structural_findings_only_for_real_change_candidates(self):
        result = MODULE.calculate(sample_input())
        self.assertEqual(
            result["structural_findings"],
            [
                {
                    "line_id": "revenue-saas",
                    "variance": Decimal("-400000"),
                    "attribution": "real_change",
                    "statement_section": "revenue",
                }
            ],
        )

        with self.subTest("timing attribution is never structural"):
            data = sample_input()
            data["structural_candidates"] = ["cogs-hosting"]
            self.assertEqual(MODULE.calculate(data)["structural_findings"], [])

        with self.subTest("real change outside the candidate list is not structural"):
            data = sample_input()
            data["structural_candidates"] = []
            self.assertEqual(MODULE.calculate(data)["structural_findings"], [])

    def test_explanation_without_evidence_is_recorded_as_missing(self):
        data = sample_input()
        data["lines"][0]["explanation_evidence"] = "unknown"
        result = MODULE.calculate(data)

        self.assertEqual(lines_by_id(result)["revenue-saas"]["attribution"], "real_change")
        self.assertIn("lines[0].explanation_evidence", result["missing_inputs"])

    def test_rejects_missing_materiality_definition_and_invalid_enums(self):
        cases = {
            "no policy and a line without a threshold": (
                lambda data: data.pop("materiality_policy"),
                "materiality must be defined by materiality_policy or by every line",
            ),
            "unknown materiality rule": (
                lambda data: data["materiality_policy"].update({"rule": "average"}),
                "rule must be one of",
            ),
            "negative absolute threshold": (
                lambda data: data["materiality_policy"].update({"absolute": money(-1, "reported")}),
                "must be nonnegative",
            ),
            "missing triage stage": (
                lambda data: data["lines"][0]["triage"].pop("mix"),
                r"triage\.mix is required",
            ),
            "unknown triage value": (
                lambda data: data["lines"][0]["triage"].update({"mix": "maybe"}),
                r"triage\.mix must be one of",
            ),
            "unknown triage stage": (
                lambda data: data["lines"][0]["triage"].update({"seasonality": "cleared"}),
                "contains unknown stages",
            ),
            "period ending after the as_of date": (
                lambda data: data["period"].update({"end": "2026-09-30"}),
                "period.end must not be after as_of_date",
            ),
            "period ending before it starts": (
                lambda data: data["period"].update({"start": "2026-09-01", "end": "2026-08-31"}),
                "period.end must not precede period.start",
            ),
            "duplicate line id": (
                lambda data: data["lines"].append(copy.deepcopy(data["lines"][0])),
                "duplicates an earlier line",
            ),
            "decomposition for an unknown line": (
                lambda data: data["volume_price_lines"][0].update({"id": "revenue-services"}),
                "must reference a line in lines",
            ),
            "duplicate decomposition": (
                lambda data: data["volume_price_lines"].append(
                    copy.deepcopy(data["volume_price_lines"][0])
                ),
                "duplicates an earlier decomposition",
            ),
            "empty segments": (
                lambda data: data["volume_price_lines"][0].update({"segments": []}),
                "segments must be a nonempty list",
            ),
            "duplicate segment id": (
                lambda data: data["volume_price_lines"][0]["segments"].append(
                    copy.deepcopy(data["volume_price_lines"][0]["segments"][0])
                ),
                "duplicates an earlier segment",
            ),
            "negative units": (
                lambda data: data["volume_price_lines"][0]["segments"][0].update(
                    {"actual_units": scalar(-1)}
                ),
                "must be nonnegative",
            ),
            "unknown segment units": (
                lambda data: data["volume_price_lines"][0]["segments"][0].update(
                    {"actual_units": {"value": None, "evidence": "unknown"}}
                ),
                "requires known units and unit prices",
            ),
            "unknown structural candidate": (
                lambda data: data.update({"structural_candidates": ["revenue-services"]}),
                "must reference a line in lines",
            ),
            "unknown statement section": (
                lambda data: data["lines"][0].update({"statement_section": "financing"}),
                "statement_section must be one of",
            ),
            "unknown comparison basis": (
                lambda data: data.update({"comparison_basis": "plan"}),
                "comparison_basis must be one of",
            ),
            "unknown amount carrying a value": (
                lambda data: data["lines"][0].update({"actual": {"amount": 1, "evidence": "unknown"}}),
                "unknown amount must be null",
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
        self.assertEqual(json.loads(valid.stdout)["period"]["label"], "2026-08")
        self.assertEqual(valid.stderr, "")
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed.stdout, "")
        self.assertIn("input error:", malformed.stderr)
        self.assertEqual(invalid_contract.returncode, 2)
        self.assertIn("input must be an object", invalid_contract.stderr)
        self.assertEqual(missing_argument.returncode, 2)
        self.assertIn("usage: analyze_budget_variance.py", missing_argument.stderr)


if __name__ == "__main__":
    unittest.main()
