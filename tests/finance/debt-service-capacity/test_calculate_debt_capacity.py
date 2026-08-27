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
    / "skills/finance/debt-service-capacity/scripts/calculate_debt_capacity.py"
)
SPEC = importlib.util.spec_from_file_location("calculate_debt_capacity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def money(amount, evidence="confirmed"):
    return {"amount": amount, "evidence": evidence}


def scalar(value, evidence="confirmed"):
    return {"value": value, "evidence": evidence}


def monthly_net(amount=350000):
    months = [f"2026-{month:02d}" for month in range(8, 13)]
    months += [f"2027-{month:02d}" for month in range(1, 8)]
    return [{"month": month, "amount": money(amount, "reported")} for month in months]


def sample_input():
    return {
        "as_of_date": "2026-08-22",
        "currency": "JPY",
        "horizon_months": 12,
        "cash_flow": {
            "period": {"start": "2025-09-01", "end": "2026-08-31"},
            "net_income_after_tax": money(4200000),
            "depreciation": money(1800000),
            "normalization_adjustments": [
                {
                    "id": "one-off-grant",
                    "label": "補助金入金",
                    "direction": "subtract",
                    "amount": money(1000000),
                }
            ],
        },
        "cash_position": {
            "available_cash": money(6000000),
            "minimum_cash_buffer": money(2000000, "reported"),
            "monthly_net_cash_before_debt_service": monthly_net(),
        },
        "loans": [
            {
                "id": "jfc-2024",
                "label": "日本政策金融公庫 2024",
                "lender_type": "government_affiliated",
                "guarantee": "none",
                "collateral": "none",
                "outstanding_principal": money(9000000),
                "annual_interest_rate_percent": scalar(1.8),
                "repayment_type": "equal_principal",
                "remaining_term_months": scalar(48),
                "grace_remaining_months": scalar(0),
                "first_payment_month": "2026-08",
                "covenants": [],
            }
        ],
        "policy": {
            "dscr_floor": scalar(1.2, "reported"),
            "debt_repayment_years_ceiling": scalar(10, "reported"),
        },
        "downside": {"cash_flow_multiplier": scalar(0.7, "estimated")},
    }


def single_loan_input(**overrides):
    data = sample_input()
    data["loans"][0].update(overrides)
    return data


class DebtServiceCapacityTests(unittest.TestCase):
    def test_calculates_equal_principal_schedule_dscr_and_repayment_years(self):
        result = MODULE.calculate(sample_input())

        self.assertEqual(result["annual_debt_service"]["principal"], 2250000)
        self.assertEqual(result["annual_debt_service"]["interest"], Decimal("143437.50"))
        self.assertEqual(result["annual_debt_service"]["total"], Decimal("2393437.50"))
        self.assertIs(result["annual_debt_service"]["annualized"], False)
        self.assertEqual(result["cash_flow"]["simple_cash_flow"], 5000000)
        self.assertEqual(result["coverage"]["dscr"], Decimal("2.089046"))
        self.assertIsNone(result["coverage"]["dscr_reason"])
        self.assertEqual(result["repayment_years"]["gross"], Decimal("1.8"))
        self.assertEqual(result["repayment_years"]["net_of_surplus_cash"], 1)
        self.assertEqual(result["debt_stock"]["surplus_cash_over_buffer"], 4000000)
        self.assertEqual(result["debt_stock"]["net_interest_bearing_debt"], 5000000)
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["missing_inputs"], [])

    def test_equal_installment_and_zero_interest_rate_schedules(self):
        with self.subTest("zero interest rate"):
            data = single_loan_input(
                outstanding_principal=money(1200000),
                annual_interest_rate_percent=scalar(0),
                repayment_type="equal_installment",
                remaining_term_months=scalar(12),
            )
            months = MODULE.calculate(data)["schedule_by_month"]
            self.assertTrue(all(month["principal"] == 100000 for month in months))
            self.assertTrue(all(month["interest"] == 0 for month in months))

        with self.subTest("positive interest rate"):
            data = single_loan_input(
                outstanding_principal=money(1200000),
                annual_interest_rate_percent=scalar(12),
                repayment_type="equal_installment",
                remaining_term_months=scalar(12),
            )
            result = MODULE.calculate(data)
            months = result["schedule_by_month"]
            self.assertEqual(months[0]["interest"], 12000)
            self.assertEqual(result["annual_debt_service"]["principal"], 1200000)
            payments = {month["principal"] + month["interest"] for month in months[:-1]}
            self.assertEqual(len(payments), 1)

    def test_grace_period_pays_interest_only_and_flags_expiry(self):
        data = single_loan_input(
            outstanding_principal=money(2400000),
            annual_interest_rate_percent=scalar(6),
            remaining_term_months=scalar(24),
            grace_remaining_months=scalar(6),
        )
        result = MODULE.calculate(data)
        months = result["schedule_by_month"]

        self.assertEqual(months[0]["principal"], 0)
        self.assertEqual(months[0]["interest"], 12000)
        self.assertEqual(months[5]["principal"], 0)
        self.assertEqual(months[6]["principal"], Decimal("133333.33"))
        codes = {(signal["code"], signal["detail"]) for signal in result["restructuring_signals"]}
        self.assertIn(
            ("grace_expiry_within_horizon", "principal repayment starts in 2027-02"), codes
        )

    def test_returns_null_dscr_when_no_scheduled_debt_service(self):
        data = single_loan_input(first_payment_month="2028-01")
        result = MODULE.calculate(data)

        self.assertEqual(result["annual_debt_service"]["total"], 0)
        self.assertIsNone(result["coverage"]["dscr"])
        self.assertEqual(result["coverage"]["dscr_reason"], "no_scheduled_debt_service")
        self.assertEqual(result["coverage"]["policy_status"], "indeterminate")
        codes = {signal["code"] for signal in result["restructuring_signals"]}
        self.assertIn("dscr_undefined", codes)

    def test_returns_null_repayment_years_for_non_positive_cash_flow(self):
        data = sample_input()
        data["cash_flow"]["net_income_after_tax"] = money(-2000000)
        data["cash_flow"]["depreciation"] = money(1000000)
        data["cash_flow"]["normalization_adjustments"] = []
        result = MODULE.calculate(data)

        self.assertEqual(result["cash_flow"]["simple_cash_flow"], -1000000)
        self.assertIsNone(result["repayment_years"]["gross"])
        self.assertIsNone(result["repayment_years"]["net_of_surplus_cash"])
        self.assertEqual(result["repayment_years"]["reason"], "non_positive_cash_flow")
        self.assertEqual(result["repayment_years"]["policy_status"], "indeterminate")
        self.assertEqual(result["cash_flow"]["downside_cash_flow"], -1000000)

    def test_headroom_reports_both_constraints_and_binding_one(self):
        proposal = {
            "principal": money(5000000, "reported"),
            "annual_interest_rate_percent": scalar(2.1, "estimated"),
            "term_months": scalar(60, "reported"),
            "grace_months": scalar(6, "reported"),
            "repayment_type": "equal_principal",
            "purpose": "working_capital",
            "drawdown_month": "2026-10",
            "first_payment_month": "2027-05",
        }

        with self.subTest("debt service coverage binds"):
            data = sample_input()
            data["proposed_borrowing"] = copy.deepcopy(proposal)
            capacity = MODULE.calculate(data)["capacity"]
            self.assertEqual(capacity["max_additional_annual_debt_service"], Decimal("1773229.17"))
            self.assertEqual(capacity["repayment_years_constraint_principal"], 45000000)
            self.assertEqual(capacity["binding_constraint"], "dscr")
            self.assertEqual(
                capacity["indicative_principal_capacity"], capacity["dscr_constraint_principal"]
            )

        with self.subTest("repayment years bind"):
            data = sample_input()
            data["proposed_borrowing"] = copy.deepcopy(proposal)
            data["policy"]["dscr_floor"] = scalar(1.05, "reported")
            data["policy"]["debt_repayment_years_ceiling"] = scalar(1.2, "reported")
            capacity = MODULE.calculate(data)["capacity"]
            self.assertEqual(capacity["repayment_years_constraint_principal"], 1000000)
            self.assertEqual(capacity["binding_constraint"], "repayment_years")
            self.assertEqual(capacity["indicative_principal_capacity"], 1000000)

    def test_policy_absent_yields_policy_not_set_and_no_classification(self):
        data = sample_input()
        del data["policy"]
        result = MODULE.calculate(data)

        self.assertEqual(result["coverage"]["policy_status"], "policy_not_set")
        self.assertEqual(result["repayment_years"]["policy_status"], "policy_not_set")
        self.assertIsNone(result["capacity"]["max_additional_annual_debt_service"])
        self.assertIsNone(result["capacity"]["repayment_years_constraint_principal"])
        self.assertEqual(result["capacity"]["binding_constraint"], "indeterminate")
        codes = {signal["code"] for signal in result["restructuring_signals"]}
        self.assertNotIn("dscr_below_floor", codes)
        self.assertNotIn("repayment_years_above_ceiling", codes)

    def test_proposed_borrowing_recomputes_coverage_and_buffer_breach(self):
        data = sample_input()
        data["proposed_borrowing"] = {
            "principal": money(5000000, "reported"),
            "annual_interest_rate_percent": scalar(2.1, "estimated"),
            "term_months": scalar(60, "reported"),
            "grace_months": scalar(6, "reported"),
            "repayment_type": "equal_principal",
            "purpose": "working_capital",
            "drawdown_month": "2026-10",
            "first_payment_month": "2027-05",
        }
        result = MODULE.calculate(data)
        proposed = result["proposed_borrowing_result"]

        self.assertEqual(proposed["annual_debt_service_after"], Decimal("2419687.50"))
        self.assertLess(proposed["dscr_after"], result["coverage"]["dscr"])
        self.assertIs(proposed["clears_dscr_floor"], True)
        self.assertIs(proposed["clears_repayment_years_ceiling"], True)
        self.assertEqual(proposed["repayment_years_after"], Decimal("2.8"))
        self.assertIsNone(proposed["buffer_breach_month"])

        with self.subTest("buffer breach after drawdown repayments"):
            tight = copy.deepcopy(data)
            tight["cash_position"]["available_cash"] = money(2100000)
            tight["cash_position"]["monthly_net_cash_before_debt_service"] = monthly_net(0)
            breached = MODULE.calculate(tight)
            self.assertEqual(breached["cash_path"]["base"]["buffer_breach_month"], "2026-08")
            codes = {signal["code"] for signal in breached["restructuring_signals"]}
            self.assertIn("buffer_breach_in_horizon", codes)

    def test_downside_multiplier_applies_only_to_cash_flow(self):
        result = MODULE.calculate(sample_input())
        base = result["cash_path"]["base"]
        downside = result["cash_path"]["downside"]

        self.assertEqual(result["cash_flow"]["downside_cash_flow"], 3500000)
        self.assertEqual(base["monthly_closing_cash"][0]["opening_cash"], 6000000)
        self.assertEqual(downside["monthly_closing_cash"][0]["opening_cash"], 6000000)
        self.assertEqual(base["monthly_closing_cash"][0]["net_cash_before_debt_service"], 350000)
        self.assertEqual(downside["monthly_closing_cash"][0]["net_cash_before_debt_service"], 245000)
        for base_month, downside_month in zip(
            base["monthly_closing_cash"], downside["monthly_closing_cash"]
        ):
            self.assertEqual(base_month["debt_service"], downside_month["debt_service"])
        self.assertLess(downside["lowest_cash"]["amount"], base["lowest_cash"]["amount"])

    def test_downside_multiplier_does_not_improve_a_burning_month(self):
        data = sample_input()
        data["cash_position"]["monthly_net_cash_before_debt_service"] = monthly_net(-100000)
        result = MODULE.calculate(data)

        self.assertEqual(
            result["cash_path"]["downside"]["monthly_closing_cash"][0][
                "net_cash_before_debt_service"
            ],
            -100000,
        )

    def test_unknown_cash_flow_component_leaves_schedule_but_nulls_coverage(self):
        data = sample_input()
        data["cash_flow"]["depreciation"] = {"amount": None, "evidence": "unknown"}
        result = MODULE.calculate(data)

        self.assertEqual(result["annual_debt_service"]["total"], Decimal("2393437.50"))
        self.assertIsNone(result["cash_flow"]["simple_cash_flow"])
        self.assertIsNone(result["coverage"]["dscr"])
        self.assertEqual(result["coverage"]["dscr_reason"], "unknown_cash_flow")
        self.assertIsNone(result["repayment_years"]["gross"])
        self.assertEqual(result["repayment_years"]["reason"], "unknown_cash_flow")
        self.assertIn("cash_flow.depreciation", result["missing_inputs"])
        self.assertEqual(result["status"], "indeterminate")

    def test_unknown_loan_terms_exclude_the_loan_and_null_coverage(self):
        data = sample_input()
        data["loans"].append(
            {
                "id": "shinkin-2025",
                "label": "信用金庫 2025",
                "lender_type": "shinkin",
                "guarantee": "credit_guarantee_association",
                "collateral": "none",
                "outstanding_principal": {"amount": None, "evidence": "unknown"},
                "annual_interest_rate_percent": scalar(2.0),
                "repayment_type": "equal_principal",
                "remaining_term_months": scalar(36),
                "grace_remaining_months": scalar(0),
                "first_payment_month": "2026-09",
            }
        )
        result = MODULE.calculate(data)

        self.assertEqual(result["debt_stock"]["excluded_loan_ids"], ["shinkin-2025"])
        self.assertIsNone(result["debt_stock"]["total_outstanding_principal"])
        self.assertIsNone(result["coverage"]["dscr"])
        self.assertEqual(result["coverage"]["dscr_reason"], "incomplete_debt_stock")
        self.assertEqual(result["repayment_years"]["reason"], "incomplete_debt_stock")
        self.assertIn("loans[1].outstanding_principal", result["missing_inputs"])

    def test_rejects_inconsistent_loan_terms(self):
        cases = {
            "custom without a schedule": (
                lambda data: data["loans"][0].update({"repayment_type": "custom"}),
                "scheduled_payments is required",
            ),
            "grace at least as long as the term": (
                lambda data: data["loans"][0].update({"grace_remaining_months": scalar(48)}),
                "shorter than the remaining term",
            ),
            "zero principal with a positive term": (
                lambda data: data["loans"][0].update({"outstanding_principal": money(0)}),
                "cannot be zero while remaining_term_months is positive",
            ),
            "interest rate above one hundred": (
                lambda data: data["loans"][0].update(
                    {"annual_interest_rate_percent": scalar(120)}
                ),
                "must not exceed 100",
            ),
            "duplicate loan id": (
                lambda data: data["loans"].append(copy.deepcopy(data["loans"][0])),
                "duplicates an earlier loan",
            ),
            "first payment before the as_of month": (
                lambda data: data["loans"][0].update({"first_payment_month": "2026-07"}),
                "must not precede the as_of_date month",
            ),
            "unknown repayment type": (
                lambda data: data["loans"][0].update({"repayment_type": "balloon"}),
                "must be a known repayment type",
            ),
            "unknown amount carrying a value": (
                lambda data: data["loans"][0].update(
                    {"outstanding_principal": {"amount": 1, "evidence": "unknown"}}
                ),
                "unknown amount must be null",
            ),
            "known evidence without an amount": (
                lambda data: data["loans"][0].update(
                    {"outstanding_principal": {"amount": None, "evidence": "confirmed"}}
                ),
                "amount is required when evidence is known",
            ),
            "negative principal": (
                lambda data: data["loans"][0].update({"outstanding_principal": money(-1)}),
                "must be nonnegative",
            ),
            "non positive dscr floor": (
                lambda data: data["policy"].update({"dscr_floor": scalar(0, "reported")}),
                "dscr_floor.value must be positive",
            ),
            "downside multiplier above one": (
                lambda data: data["downside"].update(
                    {"cash_flow_multiplier": scalar(1.5, "estimated")}
                ),
                "greater than 0 and at most 1",
            ),
            "cash flow period longer than a year": (
                lambda data: data["cash_flow"]["period"].update({"start": "2025-06-01"}),
                "about twelve months",
            ),
            "non contiguous monthly series": (
                lambda data: data["cash_position"]["monthly_net_cash_before_debt_service"][3]
                .update({"month": "2026-12"}),
                r"month must be 2026-11",
            ),
            "monthly series of the wrong length": (
                lambda data: data["cash_position"][
                    "monthly_net_cash_before_debt_service"
                ].pop(),
                "must contain exactly 12 months",
            ),
            "horizon outside the supported range": (
                lambda data: data.update({"horizon_months": 0}),
                "between 1 and 60",
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

    def test_custom_schedule_must_be_contiguous_and_within_the_horizon(self):
        base = single_loan_input(repayment_type="custom", remaining_term_months=scalar(12))
        base["loans"][0]["first_payment_month"] = "2026-08"
        payments = [
            {"month": month, "principal": money(100000), "interest": money(1000)}
            for month in [f"2026-{index:02d}" for index in range(8, 13)]
            + [f"2027-{index:02d}" for index in range(1, 8)]
        ]

        with self.subTest("accepts a full horizon schedule"):
            data = copy.deepcopy(base)
            data["loans"][0]["scheduled_payments"] = copy.deepcopy(payments)
            result = MODULE.calculate(data)
            self.assertEqual(result["annual_debt_service"]["principal"], 1200000)
            self.assertEqual(result["annual_debt_service"]["interest"], 12000)

        with self.subTest("rejects a short schedule"):
            data = copy.deepcopy(base)
            data["loans"][0]["scheduled_payments"] = copy.deepcopy(payments[:6])
            with self.assertRaisesRegex(ValueError, "must cover through 2027-07"):
                MODULE.calculate(data)

        with self.subTest("rejects a schedule past the horizon"):
            data = copy.deepcopy(base)
            extended = copy.deepcopy(payments)
            extended.append(
                {"month": "2027-08", "principal": money(100000), "interest": money(1000)}
            )
            data["loans"][0]["scheduled_payments"] = extended
            with self.assertRaisesRegex(ValueError, "must not extend past the horizon"):
                MODULE.calculate(data)

    def test_breached_covenant_raises_a_high_severity_signal(self):
        data = sample_input()
        data["loans"][0]["covenants"] = [
            {"id": "net-assets", "label": "純資産維持", "type": "financial", "status": "breached"}
        ]
        signals = MODULE.calculate(data)["restructuring_signals"]

        breach = next(signal for signal in signals if signal["code"] == "covenant_breached")
        self.assertEqual(breach["severity"], "high")
        self.assertEqual(breach["loan_id"], "jfc-2024")

    def test_short_horizon_annualizes_debt_service_and_records_it(self):
        data = sample_input()
        data["horizon_months"] = 6
        data["cash_position"]["monthly_net_cash_before_debt_service"] = monthly_net()[:6]
        annual = MODULE.calculate(data)["annual_debt_service"]

        self.assertEqual(annual["window_months"], 6)
        self.assertIs(annual["annualized"], True)
        self.assertEqual(annual["principal"], 2250000)

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
        self.assertIn("usage: calculate_debt_capacity.py", missing_argument.stderr)


if __name__ == "__main__":
    unittest.main()
