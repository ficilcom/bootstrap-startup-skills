#!/usr/bin/env python3
"""Quantify cash timing and monetary exposure from sell-side contract terms."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
CAP_TYPES = {"capped", "uncapped", "unknown"}
IP_ASSIGNMENTS = {"retained", "assigned", "unclear"}
SUBCONTRACTING = {"allowed", "prohibited", "unclear"}
POLICY_KEYS = ("max_liability_cap_ratio", "max_payment_terms_days", "max_uncovered_cost")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
DAYS_PER_MONTH = Decimal(30)


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{path} must be numeric") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{path} must be non-negative")
    return result


def _evidenced(value: object, path: str, field: str, currency: str | None = None) -> Decimal | None:
    item = _object(value, path)
    evidence = item.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be supported")
    if currency is not None and item.get("currency") != currency:
        raise ValueError(f"{path}.currency must match currency")
    raw = item.get(field)
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path}.{field} must be null when evidence is unknown")
        return None
    if raw is None:
        raise ValueError(f"{path}.{field} is required unless evidence is unknown")
    return _decimal(raw, f"{path}.{field}")


def _money(value: object, path: str, currency: str) -> Decimal | None:
    return _evidenced(value, path, "amount", currency)


def _scalar(value: object, path: str) -> Decimal | None:
    return _evidenced(value, path, "value")


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def _analysis_mode(value: object) -> str:
    mode = "core" if value is None else value
    if mode not in ANALYSIS_MODES:
        raise ValueError("analysis_mode must be core or advanced")
    return str(mode)


def _evidence_counts(value: object) -> dict[str, int]:
    counts = {state: 0 for state in sorted(EVIDENCE_STATES)}

    def visit(item: object) -> None:
        if isinstance(item, dict):
            evidence = item.get("evidence")
            if evidence in counts:
                counts[evidence] += 1
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return counts


def _months_from_days(value: Decimal) -> int:
    return int((value / DAYS_PER_MONTH).to_integral_value(rounding=ROUND_CEILING))


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    as_of = _date(data.get("as_of_date"), "as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    unknowns: list[str] = []
    warnings: list[str] = []

    contract = _object(data.get("contract"), "contract")
    contract_value = _money(contract.get("value"), "contract.value", currency)
    if contract_value is None:
        unknowns.append("contract.value")
    duration = _positive_integer(contract.get("duration_months"), "contract.duration_months")
    payment_terms = _scalar(contract.get("payment_terms_days"), "contract.payment_terms_days")
    if payment_terms is None:
        unknowns.append("contract.payment_terms_days")
    acceptance_lag = _scalar(contract.get("acceptance_lag_days"), "contract.acceptance_lag_days")
    if acceptance_lag is None:
        unknowns.append("contract.acceptance_lag_days")

    billing: list[tuple[int, Decimal | None]] = []
    seen_months: set[int] = set()
    for index, raw_event in enumerate(_list(contract.get("billing_schedule"), "contract.billing_schedule")):
        path = f"contract.billing_schedule[{index}]"
        event = _object(raw_event, path)
        month_index = event.get("month_index")
        if isinstance(month_index, bool) or not isinstance(month_index, int) or not 1 <= month_index <= duration:
            raise ValueError(f"{path}.month_index must be an integer between 1 and duration_months")
        if month_index in seen_months:
            raise ValueError("billing_schedule month_index values must be unique")
        seen_months.add(month_index)
        amount = _money(event.get("amount"), f"{path}.amount", currency)
        if amount is None:
            unknowns.append(f"{path}.amount")
        billing.append((month_index, amount))
    if not billing:
        raise ValueError("contract.billing_schedule must contain at least one event")

    raw_costs = _list(contract.get("delivery_cost_by_month"), "contract.delivery_cost_by_month")
    if len(raw_costs) != duration:
        raise ValueError("contract.delivery_cost_by_month must contain duration_months entries")
    delivery_costs: list[Decimal | None] = []
    for index, item in enumerate(raw_costs):
        amount = _money(item, f"contract.delivery_cost_by_month[{index}]", currency)
        if amount is None:
            unknowns.append(f"contract.delivery_cost_by_month[{index}]")
        delivery_costs.append(amount)

    billed_total = None if any(amount is None for _, amount in billing) else sum((amount for _, amount in billing), Decimal(0))
    if billed_total is not None and contract_value is not None and billed_total != contract_value:
        warnings.append("billing_schedule_does_not_match_contract_value")

    offset = None if payment_terms is None or acceptance_lag is None else _months_from_days(payment_terms + acceptance_lag)
    first_billing_month = min(month for month, _ in billing)
    days_to_first_cash = (
        None
        if payment_terms is None or acceptance_lag is None
        else Decimal(first_billing_month - 1) * DAYS_PER_MONTH + acceptance_lag + payment_terms
    )

    months = duration if offset is None else max(duration, max(month for month, _ in billing) + offset)
    inflows: list[Decimal | None] = [Decimal(0)] * months
    if offset is None:
        inflows = [None] * months
    else:
        for month, amount in billing:
            target = month + offset - 1
            if amount is None:
                inflows[target] = None
            elif inflows[target] is not None:
                inflows[target] += amount
    outflows: list[Decimal | None] = [Decimal(0)] * months
    for index, cost in enumerate(delivery_costs):
        outflows[index] = cost

    cumulative: list[Decimal | None] = [None] * months
    running = Decimal(0)
    truncated_at = None
    for month in range(1, months + 1):
        inflow = inflows[month - 1]
        outflow = outflows[month - 1]
        if inflow is None or outflow is None:
            truncated_at = month
            break
        running += inflow - outflow
        cumulative[month - 1] = running
    if truncated_at is not None:
        warnings.append(f"cash_path_truncated_at_month_{truncated_at}")

    known = [(month, value) for month, value in enumerate(cumulative, start=1) if value is not None]
    peak_amount = peak_month = None
    if known:
        peak_month, lowest = min(known, key=lambda item: (item[1], item[0]))
        peak_amount = max(Decimal(0), -lowest)
        if peak_amount == 0:
            peak_month = None

    policies = _object(data.get("policy_limits", {}), "policy_limits")
    policy_values: dict[str, Decimal | None] = {}
    policies_not_set: list[str] = []
    for key in POLICY_KEYS:
        raw = policies.get(key)
        if raw is None:
            policies_not_set.append(key)
            policy_values[key] = None
            continue
        value = _money(raw, f"policy_limits.{key}", currency) if key == "max_uncovered_cost" else _scalar(raw, f"policy_limits.{key}")
        policy_values[key] = value
        if value is None:
            unknowns.append(f"policy_limits.{key}")

    breached: list[str] = []
    if policy_values["max_payment_terms_days"] is not None and payment_terms is not None and payment_terms > policy_values["max_payment_terms_days"]:
        breached.append("max_payment_terms_days")
    if policy_values["max_uncovered_cost"] is not None and peak_amount is not None and peak_amount > policy_values["max_uncovered_cost"]:
        breached.append("max_uncovered_cost")

    liability: dict[str, Any] = {}
    termination: dict[str, Any] = {}
    clause_flags: list[str] = []
    priorities: list[dict[str, Any]] = []
    if mode == "advanced":
        terms = _object(data.get("terms"), "terms")
        annual_revenue = None
        if data.get("annual_revenue") is not None:
            annual_revenue = _money(data.get("annual_revenue"), "annual_revenue", currency)
            if annual_revenue is None:
                unknowns.append("annual_revenue")

        cap = _object(terms.get("liability_cap"), "terms.liability_cap")
        cap_type = cap.get("type")
        if cap_type not in CAP_TYPES:
            raise ValueError("terms.liability_cap.type must be capped, uncapped, or unknown")
        cap_amount = None
        if cap_type == "capped":
            cap_amount = _money(cap.get("amount"), "terms.liability_cap.amount", currency)
            if cap_amount is None:
                unknowns.append("terms.liability_cap")
        else:
            if cap.get("amount") is not None:
                raise ValueError("terms.liability_cap.amount must be null unless type is capped")
            if cap_type == "unknown":
                unknowns.append("terms.liability_cap")
            else:
                clause_flags.append("liability_uncapped")
        cap_to_value = None if cap_amount is None or contract_value in (None, Decimal(0)) else cap_amount / contract_value
        cap_to_revenue = None if cap_amount is None or annual_revenue in (None, Decimal(0)) else cap_amount / annual_revenue
        liability = {
            "cap_type": cap_type,
            "cap_amount": _number(cap_amount),
            "cap_to_contract_value_ratio": _number(cap_to_value),
            "cap_to_annual_revenue_ratio": _number(cap_to_revenue),
        }
        limit = policy_values["max_liability_cap_ratio"]
        if limit is not None:
            if cap_type == "uncapped":
                breached.append("max_liability_cap_ratio")
            elif cap_to_value is not None and cap_to_value > limit:
                breached.append("max_liability_cap_ratio")

        notice = _scalar(terms.get("termination_notice_days"), "terms.termination_notice_days")
        if notice is None:
            unknowns.append("terms.termination_notice_days")
        auto_renewal = terms.get("auto_renewal")
        if not isinstance(auto_renewal, bool):
            raise ValueError("terms.auto_renewal must be true or false")
        renewal_months = 0
        if auto_renewal:
            renewal_months = _positive_integer(terms.get("renewal_term_months"), "terms.renewal_term_months")
            clause_flags.append("auto_renewal_extends_commitment")
        ip_assignment = terms.get("ip_assignment")
        if ip_assignment not in IP_ASSIGNMENTS:
            raise ValueError("terms.ip_assignment must be retained, assigned, or unclear")
        if ip_assignment == "assigned":
            clause_flags.append("ip_assigned_to_customer")
        elif ip_assignment == "unclear":
            clause_flags.append("ip_assignment_unclear")
        subcontracting = terms.get("subcontracting")
        if subcontracting not in SUBCONTRACTING:
            raise ValueError("terms.subcontracting must be allowed, prohibited, or unclear")
        if subcontracting == "prohibited":
            clause_flags.append("subcontracting_prohibited")
        elif subcontracting == "unclear":
            clause_flags.append("subcontracting_unclear")

        earliest = None if notice is None else min(1 + _months_from_days(notice), duration)
        unrecovered = None
        if earliest is not None:
            value = cumulative[earliest - 1]
            unrecovered = None if value is None else max(Decimal(0), -value)
        termination = {
            "earliest_termination_month": earliest,
            "unrecovered_cost_at_earliest_termination": _number(unrecovered),
            "committed_months": duration + renewal_months,
        }

        candidates: list[tuple[str, Decimal | None, bool]] = []
        if peak_amount is not None and peak_amount > 0:
            candidates.append(("payment_terms", peak_amount, False))
        if cap_type == "uncapped":
            candidates.append(("liability_cap", None, True))
        elif cap_amount is not None:
            candidates.append(("liability_cap", cap_amount, False))
        if unrecovered is not None and unrecovered > 0:
            candidates.append(("termination_notice", unrecovered, False))
        candidates.sort(key=lambda item: (not item[2], -(item[1] or Decimal(0)), item[0]))
        priorities = [{"clause": name, "exposure": _number(amount)} for name, amount, _ in candidates]

    headline = [peak_amount, days_to_first_cash, contract_value]
    if all(value is None for value in headline):
        status = "indeterminate"
    elif unknowns or warnings:
        status = "partial"
    else:
        status = "complete"

    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "cash_path": {
            "months": months,
            "receipt_month_offset": offset,
            "days_to_first_cash": _number(days_to_first_cash),
            "inflows": [_number(value) for value in inflows],
            "outflows": [_number(value) for value in outflows],
            "cumulative_cash": [_number(value) for value in cumulative],
            "peak_funded_amount": _number(peak_amount),
            "peak_funded_month": peak_month,
            "final_cumulative_cash": _number(cumulative[months - 1]),
        },
        "billed_total": _number(billed_total),
        "breached_policy_limits": sorted(set(breached)),
        "policies_not_set": sorted(policies_not_set),
        "liability": liability,
        "termination": termination,
        "clause_flags": sorted(set(clause_flags)),
        "negotiation_priorities": priorities,
        "review_scope": "cash timing and monetary exposure from stated commercial terms only; clause validity, enforceability, legal risk, price level, and customer relationship remain separate",
        "analysis_quality": {
            "mode": mode,
            "status": status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": sorted(set(unknowns)),
            "warnings": sorted(set(warnings)),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: review_contract_terms.py <input.json>", file=sys.stderr)
        return 2
    try:
        result = calculate(json.loads(Path(args[0]).read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
