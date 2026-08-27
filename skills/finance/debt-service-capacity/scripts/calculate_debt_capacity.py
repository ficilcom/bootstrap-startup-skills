#!/usr/bin/env python3
"""Calculate debt service coverage, repayment years, and borrowing headroom from loan terms."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
EVIDENCE_RANK = {"confirmed": 3, "reported": 2, "estimated": 1, "unknown": 0}
LENDER_TYPES = {"government_affiliated", "bank", "shinkin", "credit_union", "nonbank", "other"}
GUARANTEES = {"none", "credit_guarantee_association", "personal", "other", "unknown"}
COLLATERALS = {"none", "real_estate", "deposit", "receivables", "other", "unknown"}
REPAYMENT_TYPES = {"equal_principal", "equal_installment", "bullet", "custom"}
COVENANT_STATUSES = {"met", "breached", "unknown"}
ADJUSTMENT_DIRECTIONS = {"add", "subtract"}
BORROWING_PURPOSES = {"working_capital", "capex", "refinance", "other"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CENT = Decimal("0.01")
RATE_UNIT = Decimal("0.000001")
MINIMUM_PERIOD_DAYS = 330
MAXIMUM_PERIOD_DAYS = 400


def month_index(label: str) -> int:
    year, month = label.split("-")
    return int(year) * 12 + int(month) - 1


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _parse_month(value: object, path: str) -> int:
    if not isinstance(value, str) or not MONTH_PATTERN.match(value):
        raise ValueError(f"{path} must be a YYYY-MM month")
    return month_index(value)


def _number(value: object, path: str, *, allow_negative: bool) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{path} must be finite")
    if number < 0 and not allow_negative:
        raise ValueError(f"{path} must be nonnegative")
    return number


def _evidence_entry(
    value: object,
    path: str,
    key: str,
    *,
    allow_negative: bool = False,
) -> tuple[Decimal | None, str]:
    entry = _require_object(value, path)
    evidence = entry.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    raw = entry.get(key)
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown {key} must be null")
        return None, evidence
    if raw is None:
        raise ValueError(f"{path}.{key} is required when evidence is known")
    return _number(raw, f"{path}.{key}", allow_negative=allow_negative), evidence


def _money(value: object, path: str, *, allow_negative: bool = False) -> tuple[Decimal | None, str]:
    return _evidence_entry(value, path, "amount", allow_negative=allow_negative)


def _scalar(value: object, path: str, *, allow_negative: bool = False) -> tuple[Decimal | None, str]:
    return _evidence_entry(value, path, "value", allow_negative=allow_negative)


def _integer_scalar(value: object, path: str) -> tuple[int | None, str]:
    number, evidence = _evidence_entry(value, path, "value")
    if number is None:
        return None, evidence
    if number != number.to_integral_value():
        raise ValueError(f"{path}.value must be a whole number of months")
    return int(number), evidence


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _round_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_UNIT, rounding=ROUND_HALF_UP)


def _divide(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _round_rate(numerator / denominator)


def _weakest(evidences: list[str]) -> str:
    return min(evidences, key=lambda state: EVIDENCE_RANK[state]) if evidences else "unknown"


def _monthly_series(
    value: object,
    path: str,
    *,
    start_index: int,
    length: int,
    missing: list[str],
) -> list[Decimal | None]:
    entries = _require_list(value, path)
    if len(entries) != length:
        raise ValueError(f"{path} must contain exactly {length} months")
    series: list[Decimal | None] = []
    for offset, raw_entry in enumerate(entries):
        entry_path = f"{path}[{offset}]"
        entry = _require_object(raw_entry, entry_path)
        if _parse_month(entry.get("month"), f"{entry_path}.month") != start_index + offset:
            raise ValueError(f"{entry_path}.month must be {month_label(start_index + offset)}")
        amount, _ = _money(entry.get("amount"), f"{entry_path}.amount", allow_negative=True)
        if amount is None:
            missing.append(f"{entry_path}.amount")
        series.append(amount)
    return series


def _annuity_payment(principal: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    if monthly_rate == 0:
        return principal / months
    factor = (Decimal(1) + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - Decimal(1))


def _annuity_present_value(payment: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    if monthly_rate == 0:
        return payment * months
    factor = (Decimal(1) + monthly_rate) ** months
    return payment * (factor - Decimal(1)) / (monthly_rate * factor)


def _build_schedule(
    *,
    principal: Decimal,
    annual_rate_percent: Decimal,
    repayment_type: str,
    term_months: int,
    grace_months: int,
    first_index: int,
) -> dict[int, tuple[Decimal, Decimal]]:
    """Return {month index: (principal, interest)} for one reconstructed loan."""
    monthly_rate = annual_rate_percent / Decimal(1200)
    amortizing_months = term_months - grace_months
    balance = principal
    schedule: dict[int, tuple[Decimal, Decimal]] = {}
    level_payment = (
        _annuity_payment(principal, monthly_rate, amortizing_months)
        if repayment_type == "equal_installment"
        else Decimal(0)
    )
    for offset in range(term_months):
        interest = _round_money(balance * monthly_rate)
        is_last = offset == term_months - 1
        if offset < grace_months:
            principal_due = Decimal(0)
        elif is_last:
            principal_due = balance
        elif repayment_type == "equal_principal":
            principal_due = _round_money(principal / amortizing_months)
        elif repayment_type == "equal_installment":
            principal_due = _round_money(level_payment - interest)
        else:
            principal_due = Decimal(0)
        principal_due = min(principal_due, balance)
        if principal_due < 0:
            principal_due = Decimal(0)
        balance -= principal_due
        schedule[first_index + offset] = (_round_money(principal_due), interest)
    return schedule


def _validate_custom_schedule(
    payments: object,
    *,
    path: str,
    first_index: int,
    horizon_end_index: int,
    loan_end_index: int,
) -> dict[int, tuple[Decimal, Decimal]]:
    entries = _require_list(payments, path)
    if not entries:
        raise ValueError(f"{path} must be a nonempty list")
    required_end = min(horizon_end_index, loan_end_index)
    schedule: dict[int, tuple[Decimal, Decimal]] = {}
    for offset, raw_entry in enumerate(entries):
        entry_path = f"{path}[{offset}]"
        entry = _require_object(raw_entry, entry_path)
        index = _parse_month(entry.get("month"), f"{entry_path}.month")
        if index != first_index + offset:
            raise ValueError(f"{entry_path}.month must be {month_label(first_index + offset)}")
        if index > horizon_end_index:
            raise ValueError(f"{entry_path}.month must not extend past the horizon")
        principal_due, _ = _money(entry.get("principal"), f"{entry_path}.principal")
        interest_due, _ = _money(entry.get("interest"), f"{entry_path}.interest")
        if principal_due is None or interest_due is None:
            raise ValueError(f"{entry_path} requires known principal and interest amounts")
        schedule[index] = (principal_due, interest_due)
    last_index = first_index + len(entries) - 1
    if last_index < required_end:
        raise ValueError(f"{path} must cover through {month_label(required_end)}")
    return schedule


def _parse_cash_flow(payload: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    cash_flow = _require_object(payload.get("cash_flow"), "cash_flow")
    period = _require_object(cash_flow.get("period"), "cash_flow.period")
    start = _parse_date(period.get("start"), "cash_flow.period.start")
    end = _parse_date(period.get("end"), "cash_flow.period.end")
    if end < start:
        raise ValueError("cash_flow.period.end must not precede cash_flow.period.start")
    span_days = (end - start).days + 1
    if span_days < MINIMUM_PERIOD_DAYS or span_days > MAXIMUM_PERIOD_DAYS:
        raise ValueError("cash_flow.period must cover about twelve months")

    net_income, net_income_evidence = _money(
        cash_flow.get("net_income_after_tax"), "cash_flow.net_income_after_tax", allow_negative=True
    )
    depreciation, depreciation_evidence = _money(
        cash_flow.get("depreciation"), "cash_flow.depreciation"
    )
    evidences = [net_income_evidence, depreciation_evidence]
    if net_income is None:
        missing.append("cash_flow.net_income_after_tax")
    if depreciation is None:
        missing.append("cash_flow.depreciation")

    adjustment_total = Decimal(0)
    adjustment_known = True
    seen_ids: set[str] = set()
    for index, raw_adjustment in enumerate(
        _require_list(cash_flow.get("normalization_adjustments", []), "cash_flow.normalization_adjustments")
    ):
        path = f"cash_flow.normalization_adjustments[{index}]"
        adjustment = _require_object(raw_adjustment, path)
        adjustment_id = _require_nonempty_string(adjustment.get("id"), f"{path}.id")
        if adjustment_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier normalization adjustment")
        seen_ids.add(adjustment_id)
        direction = adjustment.get("direction")
        if direction not in ADJUSTMENT_DIRECTIONS:
            raise ValueError(f"{path}.direction must be add or subtract")
        amount, evidence = _money(adjustment.get("amount"), f"{path}.amount")
        evidences.append(evidence)
        if amount is None:
            missing.append(f"{path}.amount")
            adjustment_known = False
            continue
        adjustment_total += amount if direction == "add" else -amount

    simple_cash_flow: Decimal | None = None
    if net_income is not None and depreciation is not None and adjustment_known:
        simple_cash_flow = net_income + depreciation + adjustment_total

    operating_cash_flow: Decimal | None = None
    if "operating_cash_flow" in cash_flow:
        operating_cash_flow, evidence = _money(
            cash_flow.get("operating_cash_flow"), "cash_flow.operating_cash_flow", allow_negative=True
        )
        if operating_cash_flow is None:
            missing.append("cash_flow.operating_cash_flow")
        else:
            evidences.append(evidence)

    cross_check_delta = (
        operating_cash_flow - simple_cash_flow
        if operating_cash_flow is not None and simple_cash_flow is not None
        else None
    )
    return {
        "simple_cash_flow": simple_cash_flow,
        "operating_cash_flow_reported": operating_cash_flow,
        "cross_check_delta": cross_check_delta,
        "cross_check_note": (
            "operating_cash_flow is reported for comparison only; the two bases are never averaged"
            if operating_cash_flow is not None
            else "operating_cash_flow was not supplied"
        ),
        "basis_used": "simple_cash_flow",
        "evidence_floor": _weakest(evidences),
    }


def _parse_loans(
    payload: dict[str, Any],
    *,
    as_of_index: int,
    horizon_end_index: int,
    missing: list[str],
) -> dict[str, Any]:
    loans = _require_list(payload.get("loans"), "loans")
    if not loans:
        raise ValueError("loans must be a nonempty list")

    seen_ids: set[str] = set()
    schedules: dict[str, dict[int, tuple[Decimal, Decimal]]] = {}
    outstanding_total = Decimal(0)
    outstanding_known = True
    breached_covenants: list[dict[str, str]] = []
    grace_expiries: list[dict[str, str]] = []
    bullet_maturities: list[dict[str, str]] = []
    excluded: list[str] = []

    for index, raw_loan in enumerate(loans):
        path = f"loans[{index}]"
        loan = _require_object(raw_loan, path)
        loan_id = _require_nonempty_string(loan.get("id"), f"{path}.id")
        if loan_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier loan")
        seen_ids.add(loan_id)
        _require_nonempty_string(loan.get("label"), f"{path}.label")
        if loan.get("lender_type") not in LENDER_TYPES:
            raise ValueError(f"{path}.lender_type must be a known lender type")
        if loan.get("guarantee") not in GUARANTEES:
            raise ValueError(f"{path}.guarantee must be a known guarantee state")
        if loan.get("collateral") not in COLLATERALS:
            raise ValueError(f"{path}.collateral must be a known collateral state")
        repayment_type = loan.get("repayment_type")
        if repayment_type not in REPAYMENT_TYPES:
            raise ValueError(f"{path}.repayment_type must be a known repayment type")

        principal, _ = _money(loan.get("outstanding_principal"), f"{path}.outstanding_principal")
        rate, _ = _scalar(
            loan.get("annual_interest_rate_percent"), f"{path}.annual_interest_rate_percent"
        )
        if rate is not None and rate > 100:
            raise ValueError(f"{path}.annual_interest_rate_percent must not exceed 100")
        term_months, _ = _integer_scalar(loan.get("remaining_term_months"), f"{path}.remaining_term_months")
        grace_months, _ = _integer_scalar(
            loan.get("grace_remaining_months"), f"{path}.grace_remaining_months"
        )
        if term_months is not None and term_months <= 0:
            raise ValueError(f"{path}.remaining_term_months.value must be positive")
        if grace_months is not None and term_months is not None and grace_months >= term_months:
            raise ValueError(f"{path}.grace_remaining_months.value must be shorter than the remaining term")
        if principal is not None and principal == 0 and term_months is not None and term_months > 0:
            raise ValueError(
                f"{path}.outstanding_principal cannot be zero while remaining_term_months is positive"
            )
        first_index = _parse_month(loan.get("first_payment_month"), f"{path}.first_payment_month")
        if first_index < as_of_index:
            raise ValueError(f"{path}.first_payment_month must not precede the as_of_date month")

        for covenant_index, raw_covenant in enumerate(
            _require_list(loan.get("covenants", []), f"{path}.covenants")
        ):
            covenant_path = f"{path}.covenants[{covenant_index}]"
            covenant = _require_object(raw_covenant, covenant_path)
            covenant_id = _require_nonempty_string(covenant.get("id"), f"{covenant_path}.id")
            _require_nonempty_string(covenant.get("label"), f"{covenant_path}.label")
            status = covenant.get("status")
            if status not in COVENANT_STATUSES:
                raise ValueError(f"{covenant_path}.status must be met, breached, or unknown")
            if status == "breached":
                breached_covenants.append({"loan_id": loan_id, "covenant_id": covenant_id})
            elif status == "unknown":
                missing.append(f"{covenant_path}.status")

        if repayment_type == "custom":
            if "scheduled_payments" not in loan:
                raise ValueError(f"{path}.scheduled_payments is required when repayment_type is custom")
            loan_end_index = (
                first_index + term_months - 1 if term_months is not None else horizon_end_index
            )
            schedules[loan_id] = _validate_custom_schedule(
                loan.get("scheduled_payments"),
                path=f"{path}.scheduled_payments",
                first_index=first_index,
                horizon_end_index=horizon_end_index,
                loan_end_index=loan_end_index,
            )
        elif principal is None or rate is None or term_months is None or grace_months is None:
            excluded.append(loan_id)
            for field, value in (
                ("outstanding_principal", principal),
                ("annual_interest_rate_percent", rate),
                ("remaining_term_months", term_months),
                ("grace_remaining_months", grace_months),
            ):
                if value is None:
                    missing.append(f"{path}.{field}")
        else:
            schedules[loan_id] = _build_schedule(
                principal=principal,
                annual_rate_percent=rate,
                repayment_type=repayment_type,
                term_months=term_months,
                grace_months=grace_months,
                first_index=first_index,
            )

        if principal is None:
            outstanding_known = False
        else:
            outstanding_total += principal

        if term_months is not None:
            maturity_index = first_index + term_months - 1
            if repayment_type == "bullet" and as_of_index <= maturity_index <= horizon_end_index:
                bullet_maturities.append({"loan_id": loan_id, "month": month_label(maturity_index)})
        if grace_months:
            expiry_index = first_index + grace_months
            if as_of_index <= expiry_index <= horizon_end_index:
                grace_expiries.append({"loan_id": loan_id, "month": month_label(expiry_index)})

    return {
        "schedules": schedules,
        "loan_count": len(loans),
        "total_outstanding_principal": outstanding_total if outstanding_known else None,
        "breached_covenants": breached_covenants,
        "grace_expiries": grace_expiries,
        "bullet_maturities": bullet_maturities,
        "excluded_loan_ids": excluded,
    }


def _bucket_schedule(
    schedules: dict[str, dict[int, tuple[Decimal, Decimal]]],
    *,
    as_of_index: int,
    horizon_months: int,
) -> list[dict[str, Any]]:
    months: list[dict[str, Any]] = []
    for offset in range(horizon_months):
        index = as_of_index + offset
        per_loan: dict[str, Any] = {}
        principal_total = Decimal(0)
        interest_total = Decimal(0)
        for loan_id, schedule in schedules.items():
            principal_due, interest_due = schedule.get(index, (Decimal(0), Decimal(0)))
            principal_total += principal_due
            interest_total += interest_due
            per_loan[loan_id] = {
                "principal": principal_due,
                "interest": interest_due,
                "total": principal_due + interest_due,
            }
        months.append(
            {
                "month": month_label(index),
                "principal": principal_total,
                "interest": interest_total,
                "total_debt_service": principal_total + interest_total,
                "loans": per_loan,
            }
        )
    return months


def _cash_path(
    *,
    opening_cash: Decimal | None,
    buffer_amount: Decimal | None,
    monthly_net: list[Decimal | None],
    schedule_by_month: list[dict[str, Any]],
    multiplier: Decimal | None,
) -> dict[str, Any]:
    months: list[dict[str, Any]] = []
    balance = opening_cash
    lowest: dict[str, Any] | None = None
    breach_month: str | None = None
    for offset, month_row in enumerate(schedule_by_month):
        net = monthly_net[offset]
        if net is not None and multiplier is not None and net > 0:
            net = _round_money(net * multiplier)
        closing: Decimal | None = None
        if balance is not None and net is not None:
            closing = balance + net - month_row["total_debt_service"]
        below_buffer: bool | None = None
        if closing is not None and buffer_amount is not None:
            below_buffer = closing < buffer_amount
            if below_buffer and breach_month is None:
                breach_month = month_row["month"]
        if closing is not None and (lowest is None or closing < lowest["amount"]):
            lowest = {"month": month_row["month"], "amount": closing}
        months.append(
            {
                "month": month_row["month"],
                "opening_cash": balance,
                "net_cash_before_debt_service": net,
                "debt_service": month_row["total_debt_service"],
                "closing_cash": closing,
                "below_buffer": below_buffer,
            }
        )
        balance = closing
    return {
        "monthly_closing_cash": months,
        "lowest_cash": lowest,
        "buffer_breach_month": breach_month,
    }


def _parse_proposed_borrowing(
    payload: dict[str, Any],
    *,
    as_of_index: int,
    missing: list[str],
) -> dict[str, Any] | None:
    if "proposed_borrowing" not in payload:
        return None
    path = "proposed_borrowing"
    proposal = _require_object(payload.get(path), path)
    principal, _ = _money(proposal.get("principal"), f"{path}.principal")
    rate, _ = _scalar(
        proposal.get("annual_interest_rate_percent"), f"{path}.annual_interest_rate_percent"
    )
    if rate is not None and rate > 100:
        raise ValueError(f"{path}.annual_interest_rate_percent must not exceed 100")
    term_months, _ = _integer_scalar(proposal.get("term_months"), f"{path}.term_months")
    grace_months, _ = _integer_scalar(proposal.get("grace_months"), f"{path}.grace_months")
    if term_months is not None and term_months <= 0:
        raise ValueError(f"{path}.term_months.value must be positive")
    if grace_months is not None and term_months is not None and grace_months >= term_months:
        raise ValueError(f"{path}.grace_months.value must be shorter than the term")
    repayment_type = proposal.get("repayment_type")
    if repayment_type not in REPAYMENT_TYPES or repayment_type == "custom":
        raise ValueError(f"{path}.repayment_type must be equal_principal, equal_installment, or bullet")
    if proposal.get("purpose") not in BORROWING_PURPOSES:
        raise ValueError(f"{path}.purpose must be a known borrowing purpose")
    drawdown_index = _parse_month(proposal.get("drawdown_month"), f"{path}.drawdown_month")
    first_index = _parse_month(proposal.get("first_payment_month"), f"{path}.first_payment_month")
    if drawdown_index < as_of_index:
        raise ValueError(f"{path}.drawdown_month must not precede the as_of_date month")
    if first_index < drawdown_index:
        raise ValueError(f"{path}.first_payment_month must not precede drawdown_month")
    for field, value in (
        ("principal", principal),
        ("annual_interest_rate_percent", rate),
        ("term_months", term_months),
        ("grace_months", grace_months),
    ):
        if value is None:
            missing.append(f"{path}.{field}")
    return {
        "principal": principal,
        "rate": rate,
        "term_months": term_months,
        "grace_months": grace_months,
        "repayment_type": repayment_type,
        "drawdown_index": drawdown_index,
        "first_index": first_index,
    }


def _annual_debt_service(schedule_by_month: list[dict[str, Any]], window: int) -> dict[str, Any]:
    principal = sum((row["principal"] for row in schedule_by_month[:window]), Decimal(0))
    interest = sum((row["interest"] for row in schedule_by_month[:window]), Decimal(0))
    scale = Decimal(12) / Decimal(window)
    if window != 12:
        principal = _round_money(principal * scale)
        interest = _round_money(interest * scale)
    return {
        "principal": principal,
        "interest": interest,
        "total": principal + interest,
        "window_months": window,
        "annualized": window != 12,
    }


def _capacity(
    *,
    cash_flow: Decimal | None,
    existing_annual_total: Decimal | None,
    net_interest_bearing_debt: Decimal | None,
    dscr_floor: Decimal | None,
    repayment_years_ceiling: Decimal | None,
    proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    assumptions: list[str] = []
    max_additional: Decimal | None = None
    dscr_principal: Decimal | None = None
    if cash_flow is not None and existing_annual_total is not None and dscr_floor is not None:
        headroom = cash_flow / dscr_floor - existing_annual_total
        max_additional = _round_money(headroom if headroom > 0 else Decimal(0))
        if proposal is not None and proposal["rate"] is not None and proposal["term_months"]:
            monthly_rate = proposal["rate"] / Decimal(1200)
            dscr_principal = _round_money(
                _annuity_present_value(
                    max_additional / Decimal(12), monthly_rate, proposal["term_months"]
                )
            )
            assumptions.append(
                "dscr_constraint_principal converts the annual headroom at the proposed rate and term,"
                " ignoring any grace period"
            )
        else:
            assumptions.append(
                "dscr_constraint_principal requires a proposed interest rate and term to convert"
                " annual headroom into principal"
            )

    years_principal: Decimal | None = None
    if (
        cash_flow is not None
        and net_interest_bearing_debt is not None
        and repayment_years_ceiling is not None
    ):
        room = cash_flow * repayment_years_ceiling - net_interest_bearing_debt
        years_principal = _round_money(room if room > 0 else Decimal(0))

    if dscr_principal is not None and years_principal is not None:
        binding = "dscr" if dscr_principal <= years_principal else "repayment_years"
        indicative = min(dscr_principal, years_principal)
    else:
        binding = "indeterminate"
        indicative = None
    if binding == "indeterminate":
        assumptions.append("both constraints must be computable before a binding constraint is named")
    return {
        "max_additional_annual_debt_service": max_additional,
        "dscr_constraint_principal": dscr_principal,
        "repayment_years_constraint_principal": years_principal,
        "binding_constraint": binding,
        "indicative_principal_capacity": indicative,
        "method": "annuity_present_value_at_proposed_rate_and_term",
        "assumptions": assumptions,
    }


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _signal(code: str, severity: str, loan_id: str | None, detail: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "loan_id": loan_id, "detail": detail}


def _coverage(
    *,
    cash_flow: Decimal | None,
    downside_cash_flow: Decimal | None,
    annual_debt_service: dict[str, Any],
    complete: bool,
    dscr_floor: Decimal | None,
) -> dict[str, Any]:
    service_total = annual_debt_service["total"] if complete else None
    interest_total = annual_debt_service["interest"] if complete else None
    dscr = None
    reason = None
    if service_total is None:
        reason = "incomplete_debt_stock"
    elif service_total == 0:
        reason = "no_scheduled_debt_service"
    elif cash_flow is None:
        reason = "unknown_cash_flow"
    else:
        dscr = _divide(cash_flow, service_total)
    dscr_downside = (
        _divide(downside_cash_flow, service_total)
        if service_total is not None and service_total != 0 and downside_cash_flow is not None
        else None
    )
    interest_coverage = (
        _divide(cash_flow, interest_total)
        if interest_total is not None and interest_total != 0
        else None
    )
    if dscr_floor is None:
        policy_status = "policy_not_set"
    elif dscr is None:
        policy_status = "indeterminate"
    else:
        policy_status = "within_policy" if dscr >= dscr_floor else "below_policy"
    return {
        "dscr": dscr,
        "dscr_downside": dscr_downside,
        "dscr_reason": reason,
        "interest_coverage": interest_coverage,
        "policy_status": policy_status,
        "annual_debt_service_total": service_total,
    }


def _repayment_years(
    *,
    cash_flow: Decimal | None,
    total_outstanding: Decimal | None,
    net_interest_bearing_debt: Decimal | None,
    ceiling: Decimal | None,
) -> dict[str, Any]:
    reason = None
    gross = None
    net = None
    if cash_flow is None:
        reason = "unknown_cash_flow"
    elif cash_flow <= 0:
        reason = "non_positive_cash_flow"
    elif total_outstanding is None:
        reason = "incomplete_debt_stock"
    else:
        gross = _divide(total_outstanding, cash_flow)
        net = _divide(net_interest_bearing_debt, cash_flow)
    if ceiling is None:
        policy_status = "policy_not_set"
    elif gross is None:
        policy_status = "indeterminate"
    else:
        reference = net if net is not None else gross
        policy_status = "within_policy" if reference <= ceiling else "above_ceiling"
    return {
        "gross": gross,
        "net_of_surplus_cash": net,
        "reason": reason,
        "policy_status": policy_status,
    }


def _restructuring_signals(
    *,
    coverage: dict[str, Any],
    repayment_years: dict[str, Any],
    dscr_floor: Decimal | None,
    base_path: dict[str, Any],
    loan_block: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    dscr = coverage["dscr"]
    below_floor = dscr is not None and dscr_floor is not None and dscr < dscr_floor
    if below_floor:
        signals.append(
            _signal("dscr_below_floor", "high", None, "coverage is below the policy floor supplied by the user")
        )
    if repayment_years["policy_status"] == "above_ceiling":
        signals.append(
            _signal(
                "repayment_years_above_ceiling",
                "high",
                None,
                "repayment years exceed the ceiling supplied by the user",
            )
        )
    if base_path["buffer_breach_month"] is not None:
        signals.append(
            _signal(
                "buffer_breach_in_horizon",
                "high",
                None,
                f"the base cash path falls below the buffer in {base_path['buffer_breach_month']}",
            )
        )
    for covenant in loan_block["breached_covenants"]:
        signals.append(
            _signal(
                "covenant_breached",
                "high",
                covenant["loan_id"],
                f"covenant {covenant['covenant_id']} is reported as breached",
            )
        )
    downside = coverage["dscr_downside"]
    if not below_floor and downside is not None and dscr_floor is not None and downside < dscr_floor:
        signals.append(
            _signal(
                "downside_dscr_below_floor",
                "medium",
                None,
                "coverage falls below the policy floor under the downside cash flow",
            )
        )
    for expiry in loan_block["grace_expiries"]:
        signals.append(
            _signal(
                "grace_expiry_within_horizon",
                "medium",
                expiry["loan_id"],
                f"principal repayment starts in {expiry['month']}",
            )
        )
    for maturity in loan_block["bullet_maturities"]:
        signals.append(
            _signal(
                "bullet_maturity_within_horizon",
                "medium",
                maturity["loan_id"],
                f"the full principal falls due in {maturity['month']}",
            )
        )
    if dscr is None:
        signals.append(
            _signal("dscr_undefined", "low", None, f"coverage could not be calculated: {coverage['dscr_reason']}")
        )
    return signals


def _proposed_result(
    proposal: dict[str, Any],
    *,
    loan_block: dict[str, Any],
    as_of_index: int,
    horizon_months: int,
    window: int,
    monthly_net: list[Decimal | None],
    opening_cash: Decimal | None,
    buffer_amount: Decimal | None,
    cash_flow: Decimal | None,
    total_outstanding: Decimal | None,
    dscr_floor: Decimal | None,
    ceiling: Decimal | None,
    complete: bool,
) -> dict[str, Any]:
    empty = {
        "annual_debt_service_after": None,
        "dscr_after": None,
        "repayment_years_after": None,
        "repayment_years_after_basis": "gross_outstanding_principal",
        "clears_dscr_floor": None,
        "clears_repayment_years_ceiling": None,
        "buffer_breach_month": None,
        "lowest_cash": None,
    }
    if any(
        proposal[field] is None
        for field in ("principal", "rate", "term_months", "grace_months")
    ):
        return empty

    combined = dict(loan_block["schedules"])
    combined["__proposed__"] = _build_schedule(
        principal=proposal["principal"],
        annual_rate_percent=proposal["rate"],
        repayment_type=proposal["repayment_type"],
        term_months=proposal["term_months"],
        grace_months=proposal["grace_months"],
        first_index=proposal["first_index"],
    )
    combined_schedule = _bucket_schedule(
        combined, as_of_index=as_of_index, horizon_months=horizon_months
    )
    combined_annual = _annual_debt_service(combined_schedule, window)
    combined_total = combined_annual["total"] if complete else None
    net_with_drawdown = list(monthly_net)
    drawdown_offset = proposal["drawdown_index"] - as_of_index
    if 0 <= drawdown_offset < horizon_months and net_with_drawdown[drawdown_offset] is not None:
        net_with_drawdown[drawdown_offset] += proposal["principal"]
    after_path = _cash_path(
        opening_cash=opening_cash,
        buffer_amount=buffer_amount,
        monthly_net=net_with_drawdown,
        schedule_by_month=combined_schedule,
        multiplier=None,
    )
    dscr_after = (
        _divide(cash_flow, combined_total)
        if combined_total is not None and combined_total != 0
        else None
    )
    years_after = (
        _divide(total_outstanding + proposal["principal"], cash_flow)
        if total_outstanding is not None and cash_flow is not None and cash_flow > 0
        else None
    )
    return {
        "annual_debt_service_after": combined_annual["total"],
        "dscr_after": dscr_after,
        "repayment_years_after": years_after,
        "repayment_years_after_basis": "gross_outstanding_principal",
        "clears_dscr_floor": (
            None if dscr_after is None or dscr_floor is None else dscr_after >= dscr_floor
        ),
        "clears_repayment_years_ceiling": (
            None if years_after is None or ceiling is None else years_after <= ceiling
        ),
        "buffer_breach_month": after_path["buffer_breach_month"],
        "lowest_cash": after_path["lowest_cash"],
    }


def _parse_policy(payload: dict[str, Any], missing: list[str]) -> tuple[Decimal | None, Decimal | None]:
    policy = _require_object(payload.get("policy", {}), "policy")
    floor: Decimal | None = None
    ceiling: Decimal | None = None
    if "dscr_floor" in policy:
        floor, _ = _scalar(policy.get("dscr_floor"), "policy.dscr_floor")
        if floor is None:
            missing.append("policy.dscr_floor")
        elif floor <= 0:
            raise ValueError("policy.dscr_floor.value must be positive")
    if "debt_repayment_years_ceiling" in policy:
        ceiling, _ = _scalar(
            policy.get("debt_repayment_years_ceiling"), "policy.debt_repayment_years_ceiling"
        )
        if ceiling is None:
            missing.append("policy.debt_repayment_years_ceiling")
        elif ceiling <= 0:
            raise ValueError("policy.debt_repayment_years_ceiling.value must be positive")
    return floor, ceiling


def _parse_downside(payload: dict[str, Any], missing: list[str]) -> Decimal | None:
    downside = _require_object(payload.get("downside", {}), "downside")
    if not downside:
        return None
    multiplier, _ = _scalar(downside.get("cash_flow_multiplier"), "downside.cash_flow_multiplier")
    if multiplier is None:
        missing.append("downside.cash_flow_multiplier")
    elif multiplier <= 0 or multiplier > 1:
        raise ValueError("downside.cash_flow_multiplier must be greater than 0 and at most 1")
    return multiplier


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    as_of = _parse_date(payload.get("as_of_date"), "as_of_date")
    currency = payload.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.match(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    horizon_months = payload.get("horizon_months")
    if (
        not isinstance(horizon_months, int)
        or isinstance(horizon_months, bool)
        or horizon_months < 1
        or horizon_months > 60
    ):
        raise ValueError("horizon_months must be an integer between 1 and 60")
    as_of_index = as_of.year * 12 + as_of.month - 1
    horizon_end_index = as_of_index + horizon_months - 1

    cash_flow_block = _parse_cash_flow(payload, missing)
    cash_flow = cash_flow_block["simple_cash_flow"]
    multiplier = _parse_downside(payload, missing)
    downside_cash_flow: Decimal | None = None
    if cash_flow is not None and multiplier is not None:
        downside_cash_flow = _round_money(cash_flow * multiplier) if cash_flow > 0 else cash_flow
    cash_flow_block["downside_cash_flow"] = downside_cash_flow
    cash_flow_block["multiplier_applies_to"] = "positive cash generation only"

    cash_position = _require_object(payload.get("cash_position"), "cash_position")
    available_cash, _ = _money(cash_position.get("available_cash"), "cash_position.available_cash")
    buffer_amount, _ = _money(
        cash_position.get("minimum_cash_buffer"), "cash_position.minimum_cash_buffer"
    )
    if available_cash is None:
        missing.append("cash_position.available_cash")
    if buffer_amount is None:
        missing.append("cash_position.minimum_cash_buffer")
    monthly_net = _monthly_series(
        cash_position.get("monthly_net_cash_before_debt_service"),
        "cash_position.monthly_net_cash_before_debt_service",
        start_index=as_of_index,
        length=horizon_months,
        missing=missing,
    )

    loan_block = _parse_loans(
        payload, as_of_index=as_of_index, horizon_end_index=horizon_end_index, missing=missing
    )
    schedule_by_month = _bucket_schedule(
        loan_block["schedules"], as_of_index=as_of_index, horizon_months=horizon_months
    )
    window = min(12, horizon_months)
    annual_debt_service = _annual_debt_service(schedule_by_month, window)
    complete = not loan_block["excluded_loan_ids"]

    total_outstanding = loan_block["total_outstanding_principal"]
    surplus_cash: Decimal | None = None
    if available_cash is not None and buffer_amount is not None:
        surplus_cash = max(Decimal(0), available_cash - buffer_amount)
    net_interest_bearing_debt: Decimal | None = None
    if total_outstanding is not None and surplus_cash is not None:
        net_interest_bearing_debt = total_outstanding - surplus_cash

    dscr_floor, ceiling = _parse_policy(payload, missing)
    coverage = _coverage(
        cash_flow=cash_flow,
        downside_cash_flow=downside_cash_flow,
        annual_debt_service=annual_debt_service,
        complete=complete,
        dscr_floor=dscr_floor,
    )
    service_total = coverage.pop("annual_debt_service_total")
    repayment_years = _repayment_years(
        cash_flow=cash_flow,
        total_outstanding=total_outstanding,
        net_interest_bearing_debt=net_interest_bearing_debt,
        ceiling=ceiling,
    )

    proposal = _parse_proposed_borrowing(payload, as_of_index=as_of_index, missing=missing)
    capacity = _capacity(
        cash_flow=cash_flow,
        existing_annual_total=service_total,
        net_interest_bearing_debt=net_interest_bearing_debt,
        dscr_floor=dscr_floor,
        repayment_years_ceiling=ceiling,
        proposal=proposal,
    )

    path_arguments = {
        "opening_cash": available_cash,
        "buffer_amount": buffer_amount,
        "monthly_net": monthly_net,
        "schedule_by_month": schedule_by_month,
    }
    base_path = _cash_path(multiplier=None, **path_arguments)
    downside_path = _cash_path(multiplier=multiplier, **path_arguments)

    proposed_result = (
        None
        if proposal is None
        else _proposed_result(
            proposal,
            loan_block=loan_block,
            as_of_index=as_of_index,
            horizon_months=horizon_months,
            window=window,
            monthly_net=monthly_net,
            opening_cash=available_cash,
            buffer_amount=buffer_amount,
            cash_flow=cash_flow,
            total_outstanding=total_outstanding,
            dscr_floor=dscr_floor,
            ceiling=ceiling,
            complete=complete,
        )
    )

    signals = _restructuring_signals(
        coverage=coverage,
        repayment_years=repayment_years,
        dscr_floor=dscr_floor,
        base_path=base_path,
        loan_block=loan_block,
    )
    status = (
        "computed"
        if not missing and coverage["dscr"] is not None and repayment_years["gross"] is not None
        else "indeterminate"
    )
    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "horizon_months": horizon_months,
        "horizon": {
            "start_month": month_label(as_of_index),
            "end_month": month_label(horizon_end_index),
        },
        "cash_flow": cash_flow_block,
        "debt_stock": {
            "total_outstanding_principal": total_outstanding,
            "loan_count": loan_block["loan_count"],
            "excluded_loan_ids": loan_block["excluded_loan_ids"],
            "surplus_cash_over_buffer": surplus_cash,
            "net_interest_bearing_debt": net_interest_bearing_debt,
        },
        "schedule_by_month": schedule_by_month,
        "annual_debt_service": annual_debt_service,
        "coverage": coverage,
        "repayment_years": repayment_years,
        "capacity": capacity,
        "proposed_borrowing_result": proposed_result,
        "cash_path": {"base": base_path, "downside": downside_path},
        "restructuring_signals": signals,
        "status": status,
        "missing_inputs": missing,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: calculate_debt_capacity.py <input.json>", file=sys.stderr)
        return 2
    try:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
        payload = json.loads(raw, parse_float=Decimal)
        result = calculate(_require_object(payload, "input"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
