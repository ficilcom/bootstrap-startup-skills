#!/usr/bin/env python3
"""Calculate conservative expense and SaaS audit candidates from anonymous JSON."""

from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CATEGORIES = {
    "saas", "infrastructure", "marketing", "professional_services", "contractor",
    "facilities", "insurance", "other",
}
BILLING_CYCLES = {"monthly": Decimal("12"), "quarterly": Decimal("4"), "annual": Decimal("1")}
ACTIONS = {"cancel", "downgrade", "rightsize_seats", "annualize", "renegotiate", "replace", "consolidate"}
SIGNALS = {"duplicate", "unused_or_low_utilization", "oversized", "substitutable", "renegotiable", "contract_locked"}
DEPENDENCIES = {"revenue", "customer_delivery", "data_security", "legal_regulatory", "business_continuity", "sso_api_automation"}
PROTECTED_DEPENDENCIES = DEPENDENCIES - {"sso_api_automation"}
COST_FIELDS = {"termination_fee", "migration", "reconfiguration", "training", "lost_discount"}
EFFORT_FIELDS = {"migration_hours", "reconfiguration_hours", "training_hours", "internal_hourly_cost"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _nonempty(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _date_or_null(value: object, path: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO date or null") from exc


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a nonnegative number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{path} must be finite")
    if result < 0:
        raise ValueError(f"{path} must be nonnegative")
    return result


def _evidenced_value(value: object, path: str, *, field: str) -> Decimal | None:
    entry = _require_object(value, path)
    if entry.get("evidence") not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    raw = entry.get(field)
    if entry["evidence"] == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown {field} must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.{field} is required when evidence is known")
    return _decimal(raw, f"{path}.{field}")


def _money(value: object, path: str, currency: str) -> Decimal | None:
    entry = _require_object(value, path)
    if entry.get("currency", currency) != currency:
        raise ValueError(f"{path}.currency must match top-level currency")
    return _evidenced_value(entry, path, field="amount")


def _scalar(value: object, path: str) -> Decimal | None:
    return _evidenced_value(value, path, field="value")


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    value = Decimal(value)
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(rounded) if rounded == rounded.to_integral_value() else float(rounded)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _known_sum(values: list[Decimal | None]) -> Decimal | None:
    return None if any(value is None for value in values) else sum(values, Decimal("0"))


def _validate_expense(expense: object, index: int, currency: str, as_of: date) -> dict[str, Any]:
    path = f"expense {index}"
    item = _require_object(expense, path)
    _nonempty(item.get("id"), f"{path}.id")
    _nonempty(item.get("label"), f"{path}.label")
    if item.get("category") not in CATEGORIES:
        raise ValueError(f"{path}.category must be supported")
    if item.get("billing_cycle") not in BILLING_CYCLES:
        raise ValueError(f"{path}.billing_cycle must be monthly, quarterly, or annual")
    if item.get("proposed_billing_cycle") not in BILLING_CYCLES:
        raise ValueError(f"{path}.proposed_billing_cycle must be monthly, quarterly, or annual")
    if item.get("action") not in ACTIONS:
        raise ValueError(f"{path}.action must be supported")
    _money(item.get("current_billing"), f"{path}.current_billing", currency)
    _money(item.get("proposed_billing"), f"{path}.proposed_billing", currency)
    effective = _date_or_null(item.get("effective_date"), f"{path}.effective_date")
    if effective is not None and effective < as_of:
        raise ValueError(f"{path}.effective_date must not precede as_of_date")

    signals = item.get("classification_signals")
    if not isinstance(signals, list) or any(signal not in SIGNALS for signal in signals):
        raise ValueError(f"{path}.classification_signals must contain supported signals")
    if len(set(signals)) != len(signals):
        raise ValueError(f"{path}.classification_signals must not contain duplicates")
    dependencies = item.get("dependency_flags")
    if not isinstance(dependencies, list) or any(flag not in DEPENDENCIES for flag in dependencies):
        raise ValueError(f"{path}.dependency_flags must contain supported flags")
    if len(set(dependencies)) != len(dependencies):
        raise ValueError(f"{path}.dependency_flags must not contain duplicates")

    usage = _require_object(item.get("usage"), f"{path}.usage")
    if set(usage) != {"purchased_seats", "active_seats", "unit_price"}:
        raise ValueError(f"{path}.usage must contain purchased_seats, active_seats, and unit_price")
    purchased = _scalar(usage["purchased_seats"], f"{path}.usage.purchased_seats")
    active = _scalar(usage["active_seats"], f"{path}.usage.active_seats")
    _money(usage["unit_price"], f"{path}.usage.unit_price", currency)
    if purchased is not None and active is not None and active > purchased:
        raise ValueError(f"{path}.usage.active_seats cannot exceed purchased_seats")

    contracts = _require_object(item.get("contracts"), f"{path}.contracts")
    if set(contracts) != {"renewal_date", "cancellation_notice_days", "minimum_commitment_end_date"}:
        raise ValueError(f"{path}.contracts has unsupported or missing fields")
    renewal = _date_or_null(contracts["renewal_date"], f"{path}.contracts.renewal_date")
    commitment_end = _date_or_null(contracts["minimum_commitment_end_date"], f"{path}.contracts.minimum_commitment_end_date")
    notice = contracts["cancellation_notice_days"]
    if notice is not None and (isinstance(notice, bool) or not isinstance(notice, int) or notice < 0):
        raise ValueError(f"{path}.contracts.cancellation_notice_days must be a nonnegative integer or null")

    costs = _require_object(item.get("implementation_costs"), f"{path}.implementation_costs")
    if set(costs) != COST_FIELDS:
        raise ValueError(f"{path}.implementation_costs has unsupported or missing fields")
    for field in COST_FIELDS:
        _money(costs[field], f"{path}.implementation_costs.{field}", currency)
    effort = _require_object(item.get("implementation_effort"), f"{path}.implementation_effort")
    if set(effort) != EFFORT_FIELDS:
        raise ValueError(f"{path}.implementation_effort has unsupported or missing fields")
    for field in EFFORT_FIELDS - {"internal_hourly_cost"}:
        _scalar(effort[field], f"{path}.implementation_effort.{field}")
    _money(effort["internal_hourly_cost"], f"{path}.implementation_effort.internal_hourly_cost", currency)
    return item


def validate(payload: object) -> tuple[dict[str, Any], date, str, int]:
    data = _require_object(payload, "payload")
    as_of = _date_or_null(data.get("as_of_date"), "as_of_date")
    if as_of is None:
        raise ValueError("as_of_date must be an ISO date")
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter code")
    months = data.get("analysis_months")
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 36:
        raise ValueError("analysis_months must be an integer from 1 through 36")
    expenses = data.get("expenses")
    if not isinstance(expenses, list) or not expenses:
        raise ValueError("expenses must be a nonempty list")
    ids: set[str] = set()
    for index, expense in enumerate(expenses):
        item = _validate_expense(expense, index, currency, as_of)
        if item["id"] in ids:
            raise ValueError(f"duplicate expense id {item['id']}")
        ids.add(item["id"])
    return data, as_of, currency, months


def _expense_result(item: dict[str, Any], as_of: date, currency: str, months: int) -> dict[str, Any]:
    path = f"expense {item['id']}"
    current_multiplier = BILLING_CYCLES[item["billing_cycle"]]
    proposed_multiplier = BILLING_CYCLES[item["proposed_billing_cycle"]]
    current = _money(item["current_billing"], f"{path}.current_billing", currency)
    proposed = _money(item["proposed_billing"], f"{path}.proposed_billing", currency)
    annual_savings = None if current is None or proposed is None else current * current_multiplier - proposed * proposed_multiplier
    costs = [
        _money(item["implementation_costs"][field], f"{path}.implementation_costs.{field}", currency)
        for field in sorted(COST_FIELDS)
    ]
    hours = [
        _scalar(item["implementation_effort"][field], f"{path}.implementation_effort.{field}")
        for field in ("migration_hours", "reconfiguration_hours", "training_hours")
    ]
    hourly_cost = _money(item["implementation_effort"]["internal_hourly_cost"], f"{path}.implementation_effort.internal_hourly_cost", currency)
    labor_cost = None if hourly_cost is None or any(hour is None for hour in hours) else sum(hours, Decimal("0")) * hourly_cost
    one_time = _known_sum([*costs, labor_cost])
    effective = _date_or_null(item["effective_date"], f"{path}.effective_date")
    period_end = add_months(as_of, months) - timedelta(days=1)
    eligible_days = None if effective is None else max(0, (period_end - max(as_of, effective)).days + 1)
    period_recurring = None if annual_savings is None or eligible_days is None else annual_savings * Decimal(eligible_days) / Decimal("365.2425")
    first_year = None if annual_savings is None or one_time is None else annual_savings - one_time
    period_net = None if period_recurring is None or one_time is None else period_recurring - one_time

    contracts = item["contracts"]
    renewal = _date_or_null(contracts["renewal_date"], f"{path}.contracts.renewal_date")
    notice = contracts["cancellation_notice_days"]
    deadline = None if renewal is None or notice is None else renewal - timedelta(days=notice)
    purchased = _scalar(item["usage"]["purchased_seats"], f"{path}.usage.purchased_seats")
    active = _scalar(item["usage"]["active_seats"], f"{path}.usage.active_seats")
    unit_price = _money(item["usage"]["unit_price"], f"{path}.usage.unit_price", currency)
    reasons: list[str] = []
    dependencies = set(item["dependency_flags"])
    if dependencies & PROTECTED_DEPENDENCIES:
        reasons.append("protected_dependency:" + ",".join(sorted(dependencies & PROTECTED_DEPENDENCIES)))
    if annual_savings is not None and annual_savings <= 0:
        reasons.append("no_positive_recurring_savings")
    protected = bool(dependencies & PROTECTED_DEPENDENCIES) or (annual_savings is not None and annual_savings <= 0)
    if not protected:
        if current is None or proposed is None:
            reasons.append("billing_amount_unknown")
        if one_time is None:
            reasons.append("implementation_cost_or_effort_unknown")
        if effective is None:
            reasons.append("effective_date_unknown")
        if "sso_api_automation" in dependencies:
            reasons.append("sso_api_automation_dependency")
        if item["action"] == "rightsize_seats" and (purchased is None or active is None):
            reasons.append("seat_utilization_unknown")
        if "contract_locked" in item["classification_signals"]:
            if renewal is None or notice is None or _date_or_null(contracts["minimum_commitment_end_date"], f"{path}.contracts.minimum_commitment_end_date") is None:
                reasons.append("contract_terms_unknown")
            elif effective is not None and effective < _date_or_null(contracts["minimum_commitment_end_date"], f"{path}.contracts.minimum_commitment_end_date"):
                reasons.append("minimum_commitment_not_ended")
            elif deadline is not None and as_of > deadline:
                reasons.append("cancellation_notice_deadline_passed")
    if protected:
        state = "do_not_cut"
    elif reasons:
        state = "validate_first"
    else:
        state = "safe_to_execute"
    utilization = None if purchased is None or purchased == 0 or active is None else active / purchased
    return {
        "id": item["id"], "label": item["label"], "category": item["category"], "action": item["action"],
        "billing_cycle": item["billing_cycle"], "proposed_billing_cycle": item["proposed_billing_cycle"],
        "classification_signals": item["classification_signals"], "dependency_flags": item["dependency_flags"],
        "decision_state": state, "reasons": reasons, "effective_date": item["effective_date"],
        "notification_deadline": deadline.isoformat() if deadline else None,
        "usage": {"purchased_seats": _number(purchased), "active_seats": _number(active), "unit_price": _number(unit_price), "utilization_rate": _number(utilization)},
        "costs": {"current_annual_cost": _number(None if current is None else current * current_multiplier), "proposed_annual_cost": _number(None if proposed is None else proposed * proposed_multiplier), "one_time_cost": _number(one_time), "labor_cost": _number(labor_cost)},
        "savings": {"monthly_recurring": _number(None if annual_savings is None else annual_savings / Decimal("12")), "annual_recurring": _number(annual_savings), "first_year_net": _number(first_year), "analysis_period_net": _number(period_net), "analysis_period_eligible_days": eligible_days},
    }


def _totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {"monthly_recurring": "monthly_recurring", "annual_recurring": "annual_recurring", "first_year_net": "first_year_net", "analysis_period_net": "analysis_period_net"}
    result: dict[str, Any] = {}
    for output, metric in metrics.items():
        values = [item["savings"][metric] for item in items]
        result[output] = None if any(value is None for value in values) else _number(sum((Decimal(str(value)) for value in values), Decimal("0")))
    result["incomplete"] = any(
        item["savings"][metric] is None
        for item in items
        for metric in metrics.values()
    )
    return result


def calculate(payload: object) -> dict[str, Any]:
    data, as_of, currency, months = validate(payload)
    candidates = [_expense_result(item, as_of, currency, months) for item in data["expenses"]]
    rank = {"safe_to_execute": 0, "validate_first": 1, "do_not_cut": 2}
    candidates.sort(key=lambda item: (rank[item["decision_state"]], item["notification_deadline"] or "9999-12-31", item["id"]))
    groups = {state: [item for item in candidates if item["decision_state"] == state] for state in rank}
    return {
        "as_of_date": as_of.isoformat(), "currency": currency, "analysis_months": months,
        "analysis_period_end_date": (add_months(as_of, months) - timedelta(days=1)).isoformat(),
        "candidates": candidates,
        "execution_order": [item["id"] for item in candidates if item["decision_state"] != "do_not_cut"],
        "totals_by_decision_state": {state: _totals(items) for state, items in groups.items()},
        "authorization_required": ["vendor_contact", "cancellation", "contract_or_plan_change", "payment_stop", "tool_configuration_or_data_migration"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        source = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        print(json.dumps(calculate(json.loads(source)), ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
