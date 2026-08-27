#!/usr/bin/env python3
"""Calculate aligned customer, revenue, churn, and renewal-retention metrics."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
STATUSES = {"active", "churned"}
RISK_SIGNALS = {
    "usage_decline",
    "unresolved_support",
    "payment_issue",
    "no_next_step",
    "stakeholder_change",
}
CHURN_EVIDENCE = {"customer_stated", "internal_inferred", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


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


def _money(value: object, path: str, currency: str) -> Decimal | None:
    item = _object(value, path)
    evidence = item.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be supported")
    if item.get("currency") != currency:
        raise ValueError(f"{path}.currency must match currency")
    amount = item.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path}.amount must be null when evidence is unknown")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required unless evidence is unknown")
    return _decimal(amount, f"{path}.amount")


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def _rate(numerator: Decimal, denominator: Decimal) -> float | None:
    return round(float(numerator / denominator), 6) if denominator else None


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    as_of = _date(data.get("as_of_date"), "as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    cohort = _object(data.get("cohort"), "cohort")
    cohort_start = _date(cohort.get("start_date"), "cohort.start_date")
    cohort_end = _date(cohort.get("end_date"), "cohort.end_date")
    if cohort_start > cohort_end or cohort_end > as_of:
        raise ValueError("cohort dates must satisfy start_date <= end_date <= as_of_date")
    horizon = data.get("renewal_horizon_days")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("renewal_horizon_days must be a positive integer")

    seen: set[str] = set()
    missing: list[str] = []
    customer_results: list[dict[str, Any]] = []
    customer_by_id: dict[str, dict[str, Any]] = {}
    churn_reasons: Counter[str] = Counter()
    unknown_churn_reasons = 0
    starting = ending = grr_base = expansion = contraction = churned_revenue = Decimal(0)
    financial_complete = True
    active_count = 0

    for index, raw_customer in enumerate(_list(data.get("customers"), "customers")):
        path = f"customers[{index}]"
        customer = _object(raw_customer, path)
        customer_id = _string(customer.get("id"), f"{path}.id")
        if customer_id in seen:
            raise ValueError("customer ids must be unique")
        seen.add(customer_id)
        segment = _string(customer.get("segment"), f"{path}.segment")
        status = customer.get("status")
        if status not in STATUSES:
            raise ValueError(f"{path}.status must be active or churned")
        start = _money(customer.get("start_recurring_revenue"), f"{path}.start_recurring_revenue", currency)
        end = _money(customer.get("end_recurring_revenue"), f"{path}.end_recurring_revenue", currency)
        if start is None:
            missing.append(f"{path}.start_recurring_revenue")
            financial_complete = False
        if end is None:
            missing.append(f"{path}.end_recurring_revenue")
            financial_complete = False
        if status == "churned" and end is not None and end != 0:
            raise ValueError(f"{path}.end_recurring_revenue must be zero for churned customers")
        if status == "active":
            active_count += 1
        else:
            reason = customer.get("churn_reason")
            reason_evidence = customer.get("churn_reason_evidence", "unknown")
            if reason_evidence not in CHURN_EVIDENCE:
                raise ValueError(f"{path}.churn_reason_evidence is invalid")
            if isinstance(reason, str) and reason.strip():
                churn_reasons[reason.strip()] += 1
            else:
                unknown_churn_reasons += 1

        if start is not None and end is not None:
            starting += start
            ending += end
            grr_base += min(start, end)
            expansion += max(end - start, Decimal(0))
            if status == "churned":
                churned_revenue += start
            else:
                contraction += max(start - end, Decimal(0))
        customer_result = {
            "id": customer_id,
            "segment": segment,
            "status": status,
            "start_recurring_revenue": _number(start),
            "end_recurring_revenue": _number(end),
        }
        customer_results.append(customer_result)
        customer_by_id[customer_id] = customer_result

    logo_retention = round(active_count / len(customer_results), 6) if customer_results else None

    renewal_results: list[dict[str, Any]] = []
    seen_renewals: set[str] = set()
    renewal_exposure = Decimal(0)
    renewal_exposure_complete = True
    needs_attention: list[str] = []
    for index, raw_renewal in enumerate(_list(data.get("renewals", []), "renewals")):
        path = f"renewals[{index}]"
        renewal = _object(raw_renewal, path)
        customer_id = _string(renewal.get("customer_id"), f"{path}.customer_id")
        if customer_id not in customer_by_id:
            raise ValueError(f"{path}.customer_id must reference a known customer")
        if customer_id in seen_renewals:
            raise ValueError("each customer can have at most one renewal in the review")
        seen_renewals.add(customer_id)
        renewal_date = _date(renewal.get("renewal_date"), f"{path}.renewal_date")
        revenue = _money(renewal.get("recurring_revenue"), f"{path}.recurring_revenue", currency)
        signals = _list(renewal.get("risk_signals", []), f"{path}.risk_signals")
        if len(signals) != len(set(signals)) or any(signal not in RISK_SIGNALS for signal in signals):
            raise ValueError(f"{path}.risk_signals contains an invalid or duplicate risk signal")
        risk_evidence = renewal.get("risk_evidence")
        if risk_evidence not in EVIDENCE_STATES:
            raise ValueError(f"{path}.risk_evidence must be supported")
        days = (renewal_date - as_of).days
        in_horizon = days <= horizon
        flags: list[str] = []
        if days < 0:
            flags.append("renewal_overdue")
        if signals:
            flags.append("risk_signals_present")
        if in_horizon:
            if revenue is None:
                renewal_exposure_complete = False
                missing.append(f"{path}.recurring_revenue")
            else:
                renewal_exposure += revenue
            if flags:
                needs_attention.append(customer_id)
        renewal_results.append(
            {
                "customer_id": customer_id,
                "renewal_date": renewal_date.isoformat(),
                "days_to_renewal": days,
                "in_horizon": in_horizon,
                "recurring_revenue": _number(revenue),
                "signal_count": len(signals),
                "risk_signals": signals,
                "risk_evidence": risk_evidence,
                "flags": flags,
            }
        )
    renewal_results.sort(key=lambda item: (item["renewal_date"], item["customer_id"]))

    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "financial_status": "complete" if financial_complete else "indeterminate",
        "logo_retention": logo_retention,
        "gross_revenue_retention": _rate(grr_base, starting) if financial_complete else None,
        "net_revenue_retention": _rate(ending, starting) if financial_complete else None,
        "starting_recurring_revenue": _number(starting) if financial_complete else None,
        "ending_recurring_revenue": _number(ending) if financial_complete else None,
        "expansion_revenue": _number(expansion) if financial_complete else None,
        "contraction_revenue": _number(contraction) if financial_complete else None,
        "churned_revenue": _number(churned_revenue) if financial_complete else None,
        "churn_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(churn_reasons.items(), key=lambda item: (-item[1], item[0]))
        ],
        "unknown_churn_reason_count": unknown_churn_reasons,
        "renewal_exposure": _number(renewal_exposure) if renewal_exposure_complete else None,
        "renewals_needing_attention": needs_attention,
        "customers": customer_results,
        "renewals": renewal_results,
        "missing_inputs": sorted(set(missing)),
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: calculate_retention.py <input.json>", file=sys.stderr)
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
