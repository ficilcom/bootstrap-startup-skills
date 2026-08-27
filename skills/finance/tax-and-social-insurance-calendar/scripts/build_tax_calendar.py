#!/usr/bin/env python3
"""Place supplied statutory payment obligations on a monthly cash schedule."""

from __future__ import annotations

import calendar
import json
import math
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CATEGORIES = (
    "consumption_tax",
    "corporate_tax",
    "local_corporate_taxes",
    "withholding_income_tax",
    "resident_tax_special_collection",
    "social_insurance",
    "labour_insurance",
    "other_statutory",
)
PAYMENT_STATUSES = {"scheduled", "overdue_unpaid", "paid"}
RECURRENCES = {"one_time", "monthly", "interim", "annual"}
DEFERRABLE_STATES = {"no", "requires_application", "unknown"}
CONSUMPTION_TAX_STATUSES = {"taxable", "exempt", "unknown"}
CONSUMPTION_TAX_METHODS = {"principle", "simplified", "not_applicable", "unknown"}
CONSUMPTION_TAX_INTERIM = {"none", "annual", "quarterly", "monthly", "unknown"}
CORPORATE_TAX_INTERIM = {"none", "one", "unknown"}
WITHHOLDING_EXCEPTIONS = {"none", "semiannual", "unknown"}
RESIDENT_TAX_COLLECTION = {"none", "monthly", "semiannual", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
MAXIMUM_HORIZON_MONTHS = 24


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_bounds(index: int) -> tuple[date, date]:
    year, month = index // 12, index % 12 + 1
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


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


def _require_boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _require_enum(value: object, path: str, allowed: set[str] | tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"{path} must be one of {', '.join(sorted(allowed))}")
    return str(value)


def _parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _parse_month(value: object, path: str) -> int:
    if not isinstance(value, str) or not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise ValueError(f"{path} must be a YYYY-MM month")
    year, month = value.split("-")
    return int(year) * 12 + int(month) - 1


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


def _money(value: object, path: str, *, allow_negative: bool = False) -> Decimal | None:
    entry = _require_object(value, path)
    evidence = _require_enum(entry.get("evidence"), f"{path}.evidence", EVIDENCE_STATES)
    amount = entry.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path} unknown amount must be null")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required when evidence is known")
    return _number(amount, f"{path}.amount", allow_negative=allow_negative)


def _evidence_of(value: object, path: str) -> str:
    return _require_enum(
        _require_object(value, path).get("evidence"), f"{path}.evidence", EVIDENCE_STATES
    )


def _source(value: object, path: str, *, as_of: date) -> dict[str, str]:
    entry = _require_object(value, path)
    checked_on = _parse_date(entry.get("checked_on"), f"{path}.checked_on")
    if checked_on > as_of:
        raise ValueError(f"{path}.checked_on must not be after as_of_date")
    return {
        "authority": _require_nonempty_string(entry.get("authority"), f"{path}.authority"),
        "document": _require_nonempty_string(entry.get("document"), f"{path}.document"),
        "url": _require_nonempty_string(entry.get("url"), f"{path}.url"),
        "checked_on": checked_on.isoformat(),
        "version": _require_nonempty_string(entry.get("version"), f"{path}.version"),
    }


def _parse_profile(payload: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    profile = _require_object(payload.get("profile"), "profile")
    fiscal_year_end_month = profile.get("fiscal_year_end_month")
    if (
        not isinstance(fiscal_year_end_month, int)
        or isinstance(fiscal_year_end_month, bool)
        or not 1 <= fiscal_year_end_month <= 12
    ):
        raise ValueError("profile.fiscal_year_end_month must be an integer between 1 and 12")

    consumption_status = _require_enum(
        profile.get("consumption_tax_status"),
        "profile.consumption_tax_status",
        CONSUMPTION_TAX_STATUSES,
    )
    consumption_method = _require_enum(
        profile.get("consumption_tax_method"),
        "profile.consumption_tax_method",
        CONSUMPTION_TAX_METHODS,
    )
    consumption_interim = _require_enum(
        profile.get("consumption_tax_interim"),
        "profile.consumption_tax_interim",
        CONSUMPTION_TAX_INTERIM,
    )
    corporate_interim = _require_enum(
        profile.get("corporate_tax_interim"), "profile.corporate_tax_interim", CORPORATE_TAX_INTERIM
    )
    withholding_exception = _require_enum(
        profile.get("withholding_special_exception"),
        "profile.withholding_special_exception",
        WITHHOLDING_EXCEPTIONS,
    )
    resident_tax = _require_enum(
        profile.get("resident_tax_special_collection"),
        "profile.resident_tax_special_collection",
        RESIDENT_TAX_COLLECTION,
    )
    has_employees = _require_boolean(profile.get("has_employees"), "profile.has_employees")
    pays_compensation = _require_boolean(
        profile.get("pays_withholdable_compensation"), "profile.pays_withholdable_compensation"
    )
    social_enrolled = _require_boolean(
        profile.get("social_insurance_enrolled"), "profile.social_insurance_enrolled"
    )
    labour_enrolled = _require_boolean(
        profile.get("labour_insurance_enrolled"), "profile.labour_insurance_enrolled"
    )
    employee_count: int | None = None
    count_entry = _require_object(profile.get("employee_count"), "profile.employee_count")
    count_evidence = _require_enum(
        count_entry.get("evidence"), "profile.employee_count.evidence", EVIDENCE_STATES
    )
    raw_count = count_entry.get("value")
    if count_evidence == "unknown":
        if raw_count is not None:
            raise ValueError("profile.employee_count unknown value must be null")
        missing.append("profile.employee_count")
    else:
        if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0:
            raise ValueError("profile.employee_count.value must be a nonnegative integer")
        employee_count = raw_count

    if consumption_status == "exempt" and consumption_method in {"principle", "simplified"}:
        raise ValueError("profile.consumption_tax_method contradicts consumption_tax_status")
    if consumption_status == "exempt" and consumption_interim not in {"none", "unknown"}:
        raise ValueError("profile.consumption_tax_interim contradicts consumption_tax_status")
    if has_employees and employee_count == 0:
        raise ValueError("profile.has_employees is true but employee_count.value is zero")
    if labour_enrolled and not has_employees:
        raise ValueError("profile.labour_insurance_enrolled requires has_employees to be true")

    expected: list[str] = ["corporate_tax", "local_corporate_taxes"]
    unexpected_allowed = set(expected)
    if consumption_status == "taxable":
        expected.append("consumption_tax")
    elif consumption_status == "unknown":
        missing.append("profile.consumption_tax_status")
        unexpected_allowed.add("consumption_tax")
    if pays_compensation:
        expected.append("withholding_income_tax")
    if withholding_exception == "unknown":
        missing.append("profile.withholding_special_exception")
    if resident_tax in {"monthly", "semiannual"}:
        expected.append("resident_tax_special_collection")
    elif resident_tax == "unknown":
        missing.append("profile.resident_tax_special_collection")
        unexpected_allowed.add("resident_tax_special_collection")
    if social_enrolled:
        expected.append("social_insurance")
    if labour_enrolled:
        expected.append("labour_insurance")
    if consumption_interim == "unknown":
        missing.append("profile.consumption_tax_interim")
    if corporate_interim == "unknown":
        missing.append("profile.corporate_tax_interim")

    unexpected_allowed.update(expected)
    unexpected_allowed.add("other_statutory")
    return {
        "fiscal_year_end_month": fiscal_year_end_month,
        "employee_count": employee_count,
        "expected_categories": sorted(set(expected)),
        "declared_categories": unexpected_allowed,
    }


def _parse_obligations(
    payload: dict[str, Any],
    *,
    as_of: date,
    as_of_index: int,
    horizon_end_index: int,
    missing: list[str],
) -> dict[str, Any]:
    obligations = _require_list(payload.get("obligations"), "obligations")
    seen_ids: set[str] = set()
    scheduled: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    outside_horizon: list[dict[str, Any]] = []
    excluded_paid: list[str] = []
    indeterminate: list[dict[str, Any]] = []
    supplied_categories: set[str] = set()

    for index, raw_obligation in enumerate(obligations):
        path = f"obligations[{index}]"
        obligation = _require_object(raw_obligation, path)
        obligation_id = _require_nonempty_string(obligation.get("id"), f"{path}.id")
        if obligation_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier obligation")
        seen_ids.add(obligation_id)
        label = _require_nonempty_string(obligation.get("label"), f"{path}.label")
        category = _require_enum(obligation.get("category"), f"{path}.category", CATEGORIES)
        status = _require_enum(
            obligation.get("payment_status"), f"{path}.payment_status", PAYMENT_STATUSES
        )
        _require_enum(obligation.get("recurrence"), f"{path}.recurrence", RECURRENCES)
        deferrable = _require_enum(
            obligation.get("deferrable"), f"{path}.deferrable", DEFERRABLE_STATES
        )
        if deferrable == "unknown":
            missing.append(f"{path}.deferrable")
        due_date = _parse_date(obligation.get("due_date"), f"{path}.due_date")
        _source(obligation.get("source"), f"{path}.source", as_of=as_of)
        amount = _money(obligation.get("amount"), f"{path}.amount")
        evidence = _evidence_of(obligation.get("amount"), f"{path}.amount")

        planned_raw = obligation.get("planned_payment_date")
        if status == "overdue_unpaid":
            if planned_raw is None:
                raise ValueError(
                    f"{path}.planned_payment_date is required when payment_status is overdue_unpaid"
                )
            payment_date = _parse_date(planned_raw, f"{path}.planned_payment_date")
            if payment_date < as_of:
                raise ValueError(f"{path}.planned_payment_date must not precede as_of_date")
        else:
            if planned_raw is not None:
                raise ValueError(
                    f"{path}.planned_payment_date is only allowed when payment_status is overdue_unpaid"
                )
            if status == "scheduled" and due_date < as_of:
                raise ValueError(
                    f"{path}.due_date must not precede as_of_date unless payment_status is overdue_unpaid"
                )
            payment_date = due_date

        supplied_categories.add(category)
        entry = {
            "id": obligation_id,
            "label": label,
            "category": category,
            "due_date": due_date.isoformat(),
            "planned_payment_date": payment_date.isoformat() if status == "overdue_unpaid" else None,
            "amount": amount,
            "evidence": evidence,
        }
        if status == "paid":
            excluded_paid.append(obligation_id)
            continue
        payment_index = payment_date.year * 12 + payment_date.month - 1
        if payment_index > horizon_end_index or payment_index < as_of_index:
            outside_horizon.append(entry)
            continue
        entry["month"] = month_label(payment_index)
        entry["offset"] = payment_index - as_of_index
        if amount is None:
            missing.append(f"{path}.amount")
            indeterminate.append(
                {"id": obligation_id, "category": category, "reason": "unknown_amount"}
            )
        (overdue if status == "overdue_unpaid" else scheduled).append(entry)

    return {
        "scheduled": scheduled,
        "overdue": overdue,
        "in_horizon": scheduled + overdue,
        "outside_horizon": outside_horizon,
        "excluded_paid": excluded_paid,
        "indeterminate": indeterminate,
        "supplied_categories": supplied_categories,
    }


def _monthly_baseline(
    value: object,
    *,
    as_of_index: int,
    horizon_months: int,
    missing: list[str],
) -> list[Decimal | None]:
    path = "baseline_net_cash_by_month"
    entries = _require_list(value, path)
    if len(entries) != horizon_months:
        raise ValueError(f"{path} must contain exactly {horizon_months} months")
    series: list[Decimal | None] = []
    for offset, raw_entry in enumerate(entries):
        entry_path = f"{path}[{offset}]"
        entry = _require_object(raw_entry, entry_path)
        if _parse_month(entry.get("month"), f"{entry_path}.month") != as_of_index + offset:
            raise ValueError(f"{entry_path}.month must be {month_label(as_of_index + offset)}")
        amount = _money(entry.get("amount"), f"{entry_path}.amount", allow_negative=True)
        if amount is None:
            missing.append(f"{entry_path}.amount")
        series.append(amount)
    return series


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _build_months(
    *,
    as_of: date,
    as_of_index: int,
    horizon_months: int,
    baseline: list[Decimal | None],
    in_horizon: list[dict[str, Any]],
    opening_cash: Decimal | None,
    buffer_amount: Decimal | None,
) -> dict[str, Any]:
    by_offset: dict[int, list[dict[str, Any]]] = {offset: [] for offset in range(horizon_months)}
    for obligation in in_horizon:
        by_offset[obligation["offset"]].append(obligation)

    first_indeterminate: int | None = None
    if opening_cash is None:
        first_indeterminate = 0
    for offset in range(horizon_months):
        if first_indeterminate is not None:
            break
        unknown_amount = any(item["amount"] is None for item in by_offset[offset])
        if unknown_amount or baseline[offset] is None:
            first_indeterminate = offset

    months: list[dict[str, Any]] = []
    balance = opening_cash
    first_breach: dict[str, Any] | None = None
    first_negative: str | None = None
    lowest: dict[str, Any] | None = None
    for offset in range(horizon_months):
        index = as_of_index + offset
        start, end = month_bounds(index)
        determinate = first_indeterminate is None or offset < first_indeterminate
        by_category: dict[str, Decimal] = {}
        total = Decimal(0)
        unknown_count = 0
        for item in by_offset[offset]:
            if item["amount"] is None:
                unknown_count += 1
                continue
            total += item["amount"]
            by_category[item["category"]] = by_category.get(item["category"], Decimal(0)) + item["amount"]
        opening = balance if determinate else None
        closing: Decimal | None = None
        below_buffer: bool | None = None
        if determinate and opening is not None and baseline[offset] is not None:
            closing = opening + baseline[offset] - total
            if buffer_amount is not None:
                below_buffer = closing < buffer_amount
                if below_buffer and first_breach is None:
                    first_breach = {
                        "month": month_label(index),
                        "closing_available_cash": closing,
                        "shortfall": buffer_amount - closing,
                    }
            if closing < 0 and first_negative is None:
                first_negative = month_label(index)
            if lowest is None or closing < lowest["amount"]:
                lowest = {"month": month_label(index), "amount": closing}
        months.append(
            {
                "month": month_label(index),
                "start_date": max(start, as_of).isoformat() if offset == 0 else start.isoformat(),
                "end_date": end.isoformat(),
                "statutory_payments": total,
                "statutory_payments_by_category": {
                    category: by_category[category] for category in sorted(by_category)
                },
                "unknown_obligation_count": unknown_count,
                "baseline_net_cash": baseline[offset],
                "opening_available_cash": opening,
                "closing_available_cash": closing,
                "below_buffer": below_buffer,
                "determinate": determinate,
            }
        )
        balance = closing
    determinable_through = (
        month_label(as_of_index + horizon_months - 1)
        if first_indeterminate is None
        else (month_label(as_of_index + first_indeterminate - 1) if first_indeterminate > 0 else None)
    )
    maximum_gap: Decimal | None = None
    if lowest is not None and buffer_amount is not None:
        maximum_gap = max(Decimal(0), buffer_amount - lowest["amount"])
    return {
        "months": months,
        "first_buffer_breach": first_breach,
        "first_negative_cash_month": first_negative,
        "lowest_closing_available_cash": lowest,
        "maximum_funding_gap": maximum_gap,
        "breach_determinable_through": determinable_through,
        "indeterminate_from_offset": first_indeterminate,
    }


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
        or horizon_months > MAXIMUM_HORIZON_MONTHS
    ):
        raise ValueError(f"horizon_months must be an integer between 1 and {MAXIMUM_HORIZON_MONTHS}")
    as_of_index = as_of.year * 12 + as_of.month - 1
    horizon_end_index = as_of_index + horizon_months - 1

    opening_cash = _money(payload.get("opening_available_cash"), "opening_available_cash")
    if opening_cash is None:
        missing.append("opening_available_cash")
    buffer_amount = _money(payload.get("minimum_cash_buffer"), "minimum_cash_buffer")
    if buffer_amount is None:
        missing.append("minimum_cash_buffer")
    baseline = _monthly_baseline(
        payload.get("baseline_net_cash_by_month"),
        as_of_index=as_of_index,
        horizon_months=horizon_months,
        missing=missing,
    )

    profile = _parse_profile(payload, missing)
    obligations = _parse_obligations(
        payload,
        as_of=as_of,
        as_of_index=as_of_index,
        horizon_end_index=horizon_end_index,
        missing=missing,
    )
    supplied = obligations["supplied_categories"]
    expected = profile["expected_categories"]
    coverage = {
        "expected_categories": expected,
        "supplied_categories": sorted(supplied),
        "missing_categories": sorted(set(expected) - supplied),
        "unexpected_categories": sorted(supplied - profile["declared_categories"]),
        "complete": not set(expected) - supplied,
    }

    calendar_block = _build_months(
        as_of=as_of,
        as_of_index=as_of_index,
        horizon_months=horizon_months,
        baseline=baseline,
        in_horizon=obligations["in_horizon"],
        opening_cash=opening_cash,
        buffer_amount=buffer_amount,
    )
    months = calendar_block["months"]
    ranked = sorted(
        ({"month": month["month"], "amount": month["statutory_payments"]} for month in months),
        key=lambda row: (-row["amount"], row["month"]),
    )
    peak = ranked[0] if ranked and ranked[0]["amount"] > 0 else None

    movements: list[dict[str, Any]] = []
    unmodeled: list[dict[str, str]] = []
    for obligation in obligations["in_horizon"]:
        if obligation["amount"] is None:
            unmodeled.append({"id": obligation["id"], "reason": "unknown_amount"})
            continue
        movements.append(
            {
                "target_month": obligation["month"],
                "id": f"tax-{obligation['id']}",
                "label": obligation["label"],
                "direction": "outflow",
                "amount": {"amount": obligation["amount"], "evidence": obligation["evidence"]},
            }
        )
    unmodeled.extend(
        {"id": obligation_id, "reason": "paid"} for obligation_id in obligations["excluded_paid"]
    )
    unmodeled.extend(
        {"id": obligation["id"], "reason": "outside_horizon"}
        for obligation in obligations["outside_horizon"]
    )

    status = "indeterminate" if missing or calendar_block["indeterminate_from_offset"] is not None else "computed"
    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "horizon_months": horizon_months,
        "horizon": {
            "start_month": month_label(as_of_index),
            "end_month": month_label(horizon_end_index),
        },
        "status": status,
        "coverage": coverage,
        "months": months,
        "peak_statutory_month": peak,
        "months_ranked_by_statutory_payment": ranked,
        "first_buffer_breach": calendar_block["first_buffer_breach"],
        "first_negative_cash_month": calendar_block["first_negative_cash_month"],
        "lowest_closing_available_cash": calendar_block["lowest_closing_available_cash"],
        "maximum_funding_gap": calendar_block["maximum_funding_gap"],
        "breach_determinable_through": calendar_block["breach_determinable_through"],
        "overdue_obligations": [
            {
                "id": item["id"],
                "category": item["category"],
                "due_date": item["due_date"],
                "planned_payment_date": item["planned_payment_date"],
                "amount": item["amount"],
            }
            for item in obligations["overdue"]
        ],
        "outside_horizon": [
            {
                "id": item["id"],
                "category": item["category"],
                "due_date": item["due_date"],
                "amount": item["amount"],
            }
            for item in obligations["outside_horizon"]
        ],
        "excluded_paid": obligations["excluded_paid"],
        "indeterminate_obligations": obligations["indeterminate"],
        "runway_planner_movements": movements,
        "runway_planner_unmodeled": unmodeled,
        "missing_inputs": missing,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_tax_calendar.py <input.json>", file=sys.stderr)
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
