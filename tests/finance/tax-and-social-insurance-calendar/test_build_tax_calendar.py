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
    / "skills/finance/tax-and-social-insurance-calendar/scripts/build_tax_calendar.py"
)
SPEC = importlib.util.spec_from_file_location("build_tax_calendar", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

HORIZON_MONTHS = [f"2026-{month:02d}" for month in range(8, 13)] + [
    f"2027-{month:02d}" for month in range(1, 8)
]


def money(amount, evidence="confirmed"):
    return {"amount": amount, "evidence": evidence}


def unknown_money():
    return {"amount": None, "evidence": "unknown"}


def source():
    return {
        "authority": "国税庁",
        "document": "消費税の中間申告",
        "url": "https://www.nta.go.jp/",
        "checked_on": "2026-08-22",
        "version": "記載なし",
    }


def obligation(identifier, category, due_date, amount, **overrides):
    entry = {
        "id": identifier,
        "label": f"{identifier} の納付",
        "category": category,
        "payment_status": "scheduled",
        "due_date": due_date,
        "planned_payment_date": None,
        "amount": amount,
        "recurrence": "interim",
        "deferrable": "no",
        "source": source(),
    }
    entry.update(overrides)
    return entry


def sample_input():
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "horizon_months": 12,
        "opening_available_cash": money(5200000),
        "minimum_cash_buffer": money(1500000, "reported"),
        "baseline_net_cash_by_month": [
            {"month": month, "amount": money(-200000, "reported")} for month in HORIZON_MONTHS
        ],
        "profile": {
            "fiscal_year_end_month": 3,
            "consumption_tax_status": "taxable",
            "consumption_tax_method": "simplified",
            "consumption_tax_interim": "annual",
            "corporate_tax_interim": "one",
            "has_employees": True,
            "employee_count": {"value": 4, "evidence": "confirmed"},
            "pays_withholdable_compensation": True,
            "social_insurance_enrolled": True,
            "labour_insurance_enrolled": True,
            "withholding_special_exception": "semiannual",
            "resident_tax_special_collection": "monthly",
        },
        "obligations": [
            obligation(
                "consumption-interim-1", "consumption_tax", "2026-11-30", money(480000, "estimated")
            ),
            obligation("corporate-interim", "corporate_tax", "2026-11-30", money(600000, "estimated")),
            obligation(
                "local-interim", "local_corporate_taxes", "2026-11-30", money(150000, "estimated")
            ),
            obligation(
                "withholding-h2", "withholding_income_tax", "2027-01-20", money(320000, "reported")
            ),
            obligation(
                "resident-2026-09",
                "resident_tax_special_collection",
                "2026-09-10",
                money(90000),
                recurrence="monthly",
            ),
            obligation(
                "social-2026-09",
                "social_insurance",
                "2026-09-30",
                money(420000, "reported"),
                recurrence="monthly",
                deferrable="requires_application",
            ),
            obligation("labour-2026", "labour_insurance", "2026-10-31", money(70000, "estimated")),
            obligation(
                "paid-consumption",
                "consumption_tax",
                "2026-05-31",
                money(700000),
                payment_status="paid",
                recurrence="annual",
            ),
        ],
    }


def months_by_label(result):
    return {month["month"]: month for month in result["months"]}


class BuildTaxCalendarTests(unittest.TestCase):
    def test_builds_monthly_calendar_with_running_balance_and_buffer_breach(self):
        result = MODULE.calculate(sample_input())
        months = months_by_label(result)

        self.assertEqual(months["2026-08"]["statutory_payments"], 0)
        self.assertEqual(months["2026-08"]["closing_available_cash"], 5000000)
        self.assertEqual(months["2026-09"]["statutory_payments"], 510000)
        self.assertEqual(
            months["2026-09"]["statutory_payments_by_category"],
            {"resident_tax_special_collection": Decimal("90000"), "social_insurance": Decimal("420000")},
        )
        self.assertEqual(months["2026-11"]["statutory_payments"], 1230000)
        self.assertEqual(months["2026-11"]["closing_available_cash"], 2590000)
        self.assertEqual(result["peak_statutory_month"], {"month": "2026-11", "amount": Decimal("1230000")})
        self.assertEqual(result["first_buffer_breach"]["month"], "2027-03")
        self.assertEqual(result["first_buffer_breach"]["shortfall"], 30000)
        self.assertEqual(result["maximum_funding_gap"], 830000)
        self.assertEqual(result["lowest_closing_available_cash"]["month"], "2027-07")
        self.assertIsNone(result["first_negative_cash_month"])
        self.assertEqual(result["breach_determinable_through"], "2027-07")
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["missing_inputs"], [])

    def test_unknown_obligation_amount_truncates_determinate_balances(self):
        data = sample_input()
        data["obligations"][0]["amount"] = unknown_money()
        result = MODULE.calculate(data)
        months = months_by_label(result)

        self.assertEqual(result["status"], "indeterminate")
        self.assertIs(months["2026-10"]["determinate"], True)
        self.assertEqual(months["2026-10"]["closing_available_cash"], 4020000)
        self.assertIs(months["2026-11"]["determinate"], False)
        self.assertIsNone(months["2026-11"]["closing_available_cash"])
        self.assertIsNone(months["2027-03"]["closing_available_cash"])
        self.assertEqual(months["2026-11"]["unknown_obligation_count"], 1)
        self.assertEqual(months["2026-11"]["statutory_payments"], 750000)
        self.assertEqual(result["breach_determinable_through"], "2026-10")
        self.assertIsNone(result["first_buffer_breach"])
        self.assertIn("obligations[0].amount", result["missing_inputs"])
        self.assertEqual(
            result["indeterminate_obligations"],
            [{"id": "consumption-interim-1", "category": "consumption_tax", "reason": "unknown_amount"}],
        )

    def test_unknown_opening_cash_nulls_every_balance_but_keeps_totals(self):
        data = sample_input()
        data["opening_available_cash"] = unknown_money()
        result = MODULE.calculate(data)
        months = months_by_label(result)

        self.assertTrue(all(month["closing_available_cash"] is None for month in result["months"]))
        self.assertEqual(months["2026-11"]["statutory_payments"], 1230000)
        self.assertIsNone(result["breach_determinable_through"])
        self.assertIsNone(result["maximum_funding_gap"])
        self.assertIn("opening_available_cash", result["missing_inputs"])

    def test_missing_buffer_leaves_breach_null_but_keeps_monthly_totals(self):
        data = sample_input()
        data["minimum_cash_buffer"] = unknown_money()
        result = MODULE.calculate(data)
        months = months_by_label(result)

        self.assertIsNone(result["first_buffer_breach"])
        self.assertIsNone(result["maximum_funding_gap"])
        self.assertIsNone(months["2027-03"]["below_buffer"])
        self.assertEqual(months["2026-09"]["statutory_payments"], 510000)
        self.assertEqual(months["2027-03"]["closing_available_cash"], 1470000)
        self.assertIn("minimum_cash_buffer", result["missing_inputs"])
        self.assertEqual(result["status"], "indeterminate")

    def test_coverage_reports_missing_and_unexpected_categories(self):
        with self.subTest("declared but not supplied"):
            data = sample_input()
            data["obligations"] = [
                item for item in data["obligations"] if item["category"] != "labour_insurance"
            ]
            coverage = MODULE.calculate(data)["coverage"]
            self.assertEqual(coverage["missing_categories"], ["labour_insurance"])
            self.assertIs(coverage["complete"], False)

        with self.subTest("supplied though the profile excludes it"):
            data = sample_input()
            data["profile"]["consumption_tax_status"] = "exempt"
            data["profile"]["consumption_tax_method"] = "not_applicable"
            data["profile"]["consumption_tax_interim"] = "none"
            coverage = MODULE.calculate(data)["coverage"]
            self.assertEqual(coverage["unexpected_categories"], ["consumption_tax"])
            self.assertNotIn("consumption_tax", coverage["expected_categories"])

        with self.subTest("unknown status is neither expected nor unexpected"):
            data = sample_input()
            data["profile"]["consumption_tax_status"] = "unknown"
            result = MODULE.calculate(data)
            coverage = result["coverage"]
            self.assertNotIn("consumption_tax", coverage["expected_categories"])
            self.assertEqual(coverage["unexpected_categories"], [])
            self.assertIn("profile.consumption_tax_status", result["missing_inputs"])

    def test_overdue_obligation_is_bucketed_at_planned_payment_date(self):
        data = sample_input()
        data["obligations"][4].update(
            {
                "payment_status": "overdue_unpaid",
                "due_date": "2026-07-10",
                "planned_payment_date": "2026-10-15",
            }
        )
        result = MODULE.calculate(data)
        months = months_by_label(result)

        self.assertEqual(months["2026-09"]["statutory_payments"], 420000)
        self.assertEqual(months["2026-10"]["statutory_payments"], 160000)
        self.assertEqual(
            result["overdue_obligations"],
            [
                {
                    "id": "resident-2026-09",
                    "category": "resident_tax_special_collection",
                    "due_date": "2026-07-10",
                    "planned_payment_date": "2026-10-15",
                    "amount": Decimal("90000"),
                }
            ],
        )

        cases = {
            "overdue without a planned payment date": (
                lambda payload: payload["obligations"][4].update(
                    {"payment_status": "overdue_unpaid", "due_date": "2026-07-10"}
                ),
                "planned_payment_date is required",
            ),
            "planned payment date in the past": (
                lambda payload: payload["obligations"][4].update(
                    {
                        "payment_status": "overdue_unpaid",
                        "due_date": "2026-07-10",
                        "planned_payment_date": "2026-08-01",
                    }
                ),
                "planned_payment_date must not precede as_of_date",
            ),
            "scheduled obligation already past due": (
                lambda payload: payload["obligations"][4].update({"due_date": "2026-07-10"}),
                "must not precede as_of_date unless payment_status is overdue_unpaid",
            ),
            "planned payment date on a scheduled obligation": (
                lambda payload: payload["obligations"][4].update(
                    {"planned_payment_date": "2026-10-15"}
                ),
                "only allowed when payment_status is overdue_unpaid",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name):
                payload = sample_input()
                mutate(payload)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.calculate(payload)

    def test_reports_obligations_outside_the_horizon_without_dropping_them(self):
        data = sample_input()
        data["obligations"].append(
            obligation("consumption-final", "consumption_tax", "2027-11-30", money(900000, "estimated"))
        )
        result = MODULE.calculate(data)

        self.assertEqual(
            result["outside_horizon"],
            [
                {
                    "id": "consumption-final",
                    "category": "consumption_tax",
                    "due_date": "2027-11-30",
                    "amount": Decimal("900000"),
                }
            ],
        )
        self.assertIn(
            {"id": "consumption-final", "reason": "outside_horizon"},
            result["runway_planner_unmodeled"],
        )

    def test_exports_runway_planner_movements_and_excludes_unknown_and_paid(self):
        data = sample_input()
        data["obligations"][6]["amount"] = unknown_money()
        result = MODULE.calculate(data)
        movements = result["runway_planner_movements"]

        self.assertEqual(len(movements), 6)
        first = next(item for item in movements if item["id"] == "tax-consumption-interim-1")
        self.assertEqual(
            set(first),
            {"target_month", "id", "label", "direction", "amount"},
        )
        self.assertEqual(first["direction"], "outflow")
        self.assertEqual(first["target_month"], "2026-11")
        self.assertEqual(first["amount"], {"amount": Decimal("480000"), "evidence": "estimated"})
        self.assertTrue(all(item["id"].startswith("tax-") for item in movements))
        self.assertNotIn("tax-paid-consumption", {item["id"] for item in movements})
        self.assertIn({"id": "labour-2026", "reason": "unknown_amount"}, result["runway_planner_unmodeled"])
        self.assertIn({"id": "paid-consumption", "reason": "paid"}, result["runway_planner_unmodeled"])
        self.assertEqual(result["excluded_paid"], ["paid-consumption"])

    def test_rejects_contradictory_profile_and_malformed_money(self):
        cases = {
            "simplified method while exempt": (
                lambda data: data["profile"].update({"consumption_tax_status": "exempt"}),
                "consumption_tax_method contradicts",
            ),
            "interim payments while exempt": (
                lambda data: data["profile"].update(
                    {"consumption_tax_status": "exempt", "consumption_tax_method": "not_applicable"}
                ),
                "consumption_tax_interim contradicts",
            ),
            "employees with a zero headcount": (
                lambda data: data["profile"].update(
                    {"employee_count": {"value": 0, "evidence": "confirmed"}}
                ),
                "employee_count.value is zero",
            ),
            "labour insurance without employees": (
                lambda data: data["profile"].update(
                    {
                        "has_employees": False,
                        "employee_count": {"value": 0, "evidence": "confirmed"},
                    }
                ),
                "labour_insurance_enrolled requires has_employees",
            ),
            "fiscal year end out of range": (
                lambda data: data["profile"].update({"fiscal_year_end_month": 13}),
                "between 1 and 12",
            ),
            "negative headcount": (
                lambda data: data["profile"].update(
                    {"employee_count": {"value": -1, "evidence": "confirmed"}}
                ),
                "nonnegative integer",
            ),
            "unknown amount carrying a value": (
                lambda data: data["obligations"][0].update(
                    {"amount": {"amount": 1, "evidence": "unknown"}}
                ),
                "unknown amount must be null",
            ),
            "known evidence without an amount": (
                lambda data: data["obligations"][0].update(
                    {"amount": {"amount": None, "evidence": "confirmed"}}
                ),
                "amount is required when evidence is known",
            ),
            "negative amount": (
                lambda data: data["obligations"][0].update({"amount": money(-1)}),
                "must be nonnegative",
            ),
            "duplicate obligation id": (
                lambda data: data["obligations"].append(copy.deepcopy(data["obligations"][0])),
                "duplicates an earlier obligation",
            ),
            "unknown category": (
                lambda data: data["obligations"][0].update({"category": "stamp_duty"}),
                "category must be one of",
            ),
            "source checked after the as_of date": (
                lambda data: data["obligations"][0]["source"].update({"checked_on": "2026-08-23"}),
                "checked_on must not be after as_of_date",
            ),
            "horizon beyond the supported range": (
                lambda data: data.update({"horizon_months": 25}),
                "between 1 and 24",
            ),
            "malformed currency": (
                lambda data: data.update({"currency": "yen"}),
                "three-letter uppercase code",
            ),
        }
        for name, (mutate, message) in cases.items():
            with self.subTest(name):
                data = sample_input()
                mutate(data)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.calculate(data)

    def test_rejects_non_contiguous_or_short_baseline_series(self):
        with self.subTest("wrong length"):
            data = sample_input()
            data["baseline_net_cash_by_month"].pop()
            with self.assertRaisesRegex(ValueError, "must contain exactly 12 months"):
                MODULE.calculate(data)

        with self.subTest("non contiguous months"):
            data = sample_input()
            data["baseline_net_cash_by_month"][3]["month"] = "2026-12"
            with self.assertRaisesRegex(ValueError, "month must be 2026-11"):
                MODULE.calculate(data)

        with self.subTest("does not start at the as_of month"):
            data = sample_input()
            data["baseline_net_cash_by_month"] = [
                {"month": month, "amount": money(-200000, "reported")}
                for month in HORIZON_MONTHS[1:] + ["2027-08"]
            ]
            with self.assertRaisesRegex(ValueError, "month must be 2026-08"):
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
        self.assertIn("usage: build_tax_calendar.py", missing_argument.stderr)


if __name__ == "__main__":
    unittest.main()
