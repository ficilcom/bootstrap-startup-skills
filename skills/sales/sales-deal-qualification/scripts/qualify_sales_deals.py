#!/usr/bin/env python3
"""Qualify sales deals from explicit evidence and gates."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
IMPORTANCE = {"must", "should"}
RESULT_STATUSES = {"verified", "reported", "unknown", "failed"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
ADVANCED_CHECKS = ("decision_process", "mutual_action_plan", "commercial_terms")


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "a non-empty list" if nonempty else "a list"
        raise ValueError(f"{path} must be {qualifier}")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _date(value: object, path: str) -> date:
    text = _string(value, path)
    try:
        return date.fromisoformat(text)
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


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    as_of = _date(data.get("as_of_date"), "as_of_date")
    forecast_end = _date(data.get("forecast_end_date"), "forecast_end_date")
    if forecast_end < as_of:
        raise ValueError("forecast_end_date must not be before as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    intervention_threshold = _money(data.get("founder_intervention_threshold"), "founder_intervention_threshold", currency)

    criteria: dict[str, str] = {}
    for index, raw_criterion in enumerate(_list(data.get("criteria"), "criteria", nonempty=True)):
        path = f"criteria[{index}]"
        criterion = _object(raw_criterion, path)
        criterion_id = _string(criterion.get("id"), f"{path}.id")
        if criterion_id in criteria:
            raise ValueError("criterion ids must be unique")
        importance = criterion.get("importance")
        if importance not in IMPORTANCE:
            raise ValueError(f"{path}.importance must be must or should")
        criteria[criterion_id] = str(importance)

    decision_unknowns: list[str] = []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_deal in enumerate(_list(data.get("deals"), "deals", nonempty=True)):
        path = f"deals[{index}]"
        deal = _object(raw_deal, path)
        deal_id = _string(deal.get("id"), f"{path}.id")
        if deal_id in seen:
            raise ValueError("deal ids must be unique")
        seen.add(deal_id)
        customer_id = _string(deal.get("customer_id"), f"{path}.customer_id")
        amount = _money(deal.get("amount"), f"{path}.amount", currency)
        probability = _scalar(deal.get("stage_probability"), f"{path}.stage_probability")
        if probability is not None and probability > 1:
            raise ValueError(f"{path}.stage_probability must be between 0 and 1")
        if amount is None:
            decision_unknowns.append(f"{path}.amount")
        if probability is None:
            decision_unknowns.append(f"{path}.stage_probability")
        close_date = _date(deal.get("close_date"), f"{path}.close_date")
        next_action_date = _date(deal.get("next_action_date"), f"{path}.next_action_date")

        statuses: dict[str, str] = {}
        for result_index, raw_result in enumerate(_list(deal.get("qualification_results"), f"{path}.qualification_results")):
            result_path = f"{path}.qualification_results[{result_index}]"
            result = _object(raw_result, result_path)
            criterion_id = _string(result.get("id"), f"{result_path}.id")
            if criterion_id not in criteria:
                raise ValueError(f"{result_path} references unknown criterion {criterion_id}")
            if criterion_id in statuses:
                raise ValueError(f"{path}.qualification_results ids must be unique")
            status = result.get("status")
            if status not in RESULT_STATUSES:
                raise ValueError(f"{result_path}.status must be supported")
            statuses[criterion_id] = str(status)

        failed_gates = sorted(criterion_id for criterion_id, importance in criteria.items() if importance == "must" and statuses.get(criterion_id) == "failed")
        unverified_gates = sorted(criterion_id for criterion_id, importance in criteria.items() if importance == "must" and statuses.get(criterion_id) != "verified" and criterion_id not in failed_gates)
        validation_targets = sorted(criterion_id for criterion_id, status in statuses.items() if status in {"reported", "unknown"})
        for criterion_id in unverified_gates:
            decision_unknowns.append(f"{path}.criteria.{criterion_id}")

        if mode == "advanced":
            for check in ADVANCED_CHECKS:
                field = f"{check}_status"
                status = deal.get(field)
                if status not in RESULT_STATUSES:
                    raise ValueError(f"{path}.{field} must be supported")
                if status == "failed":
                    failed_gates.append(check)
                elif status != "verified":
                    unverified_gates.append(check)
                    validation_targets.append(check)
                    decision_unknowns.append(f"{path}.{field}")

        failed_gates = sorted(set(failed_gates))
        unverified_gates = sorted(set(unverified_gates))
        validation_targets = sorted(set(validation_targets))
        eligibility = "disqualified" if failed_gates else "conditional" if unverified_gates else "qualified"
        weighted = amount * probability if amount is not None and probability is not None else None
        timing_flags: list[str] = []
        if close_date < as_of:
            timing_flags.append("close_date_overdue")
        if close_date > forecast_end:
            timing_flags.append("forecast_period_outside")
        if next_action_date < as_of:
            timing_flags.append("next_action_overdue")
        high_value = amount is not None and intervention_threshold is not None and amount >= intervention_threshold
        if intervention_threshold is None:
            decision_unknowns.append("founder_intervention_threshold")
        if failed_gates:
            action = "exit"
        elif unverified_gates or timing_flags:
            action = "founder_intervention" if high_value else "hold"
        else:
            action = "continue"
        flags = list(timing_flags)
        if failed_gates:
            flags.append("failed_must_gate")
        if unverified_gates:
            flags.append("unverified_gate")
        results.append({
            "id": deal_id,
            "customer_id": customer_id,
            "weighted_amount": _number(weighted),
            "eligibility_status": eligibility,
            "failed_gates": failed_gates,
            "unverified_gates": unverified_gates,
            "timing_flags": timing_flags,
            "recommended_action": action,
            "validation_targets": validation_targets,
            "flags": sorted(flags),
        })

    ranked = [item for item in results if item["weighted_amount"] is not None]
    ranked.sort(key=lambda item: (-item["weighted_amount"], item["id"]))
    unknowns = sorted(set(decision_unknowns))
    if not ranked:
        quality_status = "indeterminate"
    elif unknowns:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in results for flag in item["flags"]})
    return {
        "as_of_date": as_of.isoformat(),
        "forecast_end_date": forecast_end.isoformat(),
        "currency": currency,
        "deals": results,
        "weighted_order": [item["id"] for item in ranked],
        "ranking_scope": "user-supplied probability weighted amount only; qualification, timing, concentration, terms, and intervention gates remain separate",
        "analysis_quality": {
            "mode": mode,
            "status": quality_status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": unknowns,
            "warnings": warnings,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: qualify_sales_deals.py <input.json>", file=sys.stderr)
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
