#!/usr/bin/env python3
"""Assess evidence-backed answerability of a customer security questionnaire against its deadline."""

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
REQUIREMENT_LEVELS = ("must", "should", "optional")
CURRENT_STATES = {"implemented", "partial", "not_implemented", "unknown"}
EVIDENCE_ARTIFACTS = {"document", "configuration", "log", "third_party", "none", "unknown"}
USABLE_ARTIFACTS = {"document", "configuration", "log", "third_party"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
DAYS_PER_WEEK = Decimal(7)


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


def _hours(value: object, path: str) -> Decimal | None:
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
    deadline = _date(data.get("submission_deadline"), "submission_deadline")
    if deadline <= as_of:
        raise ValueError("submission_deadline must be after as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    unknowns: list[str] = []
    warnings: list[str] = []

    weekly_hours = _hours(data.get("available_hours_per_week"), "available_hours_per_week")
    if weekly_hours is None:
        unknowns.append("available_hours_per_week")
    elif weekly_hours == 0:
        raise ValueError("available_hours_per_week.value must be greater than zero")

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(_list(data.get("items"), "items")):
        path = f"items[{index}]"
        entry = _object(raw_item, path)
        item_id = _string(entry.get("id"), f"{path}.id")
        if item_id in seen_ids:
            raise ValueError("item ids must be unique")
        seen_ids.add(item_id)
        category = _string(entry.get("category"), f"{path}.category")
        level = entry.get("requirement_level")
        if level not in REQUIREMENT_LEVELS:
            raise ValueError(f"{path}.requirement_level must be must, should, or optional")
        state = entry.get("current_state")
        if state not in CURRENT_STATES:
            raise ValueError(f"{path}.current_state must be implemented, partial, not_implemented, or unknown")
        artifact = entry.get("evidence_artifact")
        if artifact not in EVIDENCE_ARTIFACTS:
            raise ValueError(f"{path}.evidence_artifact must be a supported artifact type")
        if state == "unknown":
            unknowns.append(f"{path}.current_state")
        if artifact == "unknown":
            unknowns.append(f"{path}.evidence_artifact")
        remediation = _hours(entry.get("remediation_hours"), f"{path}.remediation_hours")
        answerable = state == "implemented" and artifact in USABLE_ARTIFACTS
        cost = None
        if mode == "advanced" and entry.get("remediation_cost") is not None:
            cost = _money(entry.get("remediation_cost"), f"{path}.remediation_cost", currency)
        owner = entry.get("owner")
        if owner is not None:
            owner = _string(owner, f"{path}.owner")
        if not answerable and remediation is None:
            unknowns.append(f"{path}.remediation_hours")
        items.append(
            {
                "id": item_id,
                "path": path,
                "category": category,
                "requirement_level": level,
                "current_state": state,
                "evidence_artifact": artifact,
                "remediation_hours": remediation,
                "remediation_cost": cost,
                "owner": owner,
                "answerable_now": answerable,
            }
        )
    if not items:
        raise ValueError("items must contain at least one item")

    gaps = [entry for entry in items if not entry["answerable_now"]]
    must_gaps = [entry for entry in gaps if entry["requirement_level"] == "must"]

    categories: dict[str, dict[str, int]] = {}
    for entry in items:
        bucket = categories.setdefault(entry["category"], {"items": 0, "answerable_now": 0, "must_items": 0, "must_gaps": 0})
        bucket["items"] += 1
        if entry["answerable_now"]:
            bucket["answerable_now"] += 1
        if entry["requirement_level"] == "must":
            bucket["must_items"] += 1
            if not entry["answerable_now"]:
                bucket["must_gaps"] += 1
    category_coverage = [
        {
            "category": name,
            **bucket,
            "coverage_rate": _number(Decimal(bucket["answerable_now"]) / Decimal(bucket["items"])),
        }
        for name, bucket in sorted(categories.items())
    ]

    weeks_available = Decimal((deadline - as_of).days) / DAYS_PER_WEEK
    order = {level: index for index, level in enumerate(REQUIREMENT_LEVELS)}
    ordered = sorted(
        gaps,
        key=lambda entry: (
            order[entry["requirement_level"]],
            entry["remediation_hours"] is None,
            entry["remediation_hours"] if entry["remediation_hours"] is not None else Decimal(0),
            entry["id"],
        ),
    )

    schedule: list[dict[str, Any]] = []
    cumulative: Decimal | None = Decimal(0)
    known_floor = Decimal(0)
    first_past: str | None = None
    for entry in ordered:
        remediation = entry["remediation_hours"]
        if remediation is None:
            cumulative = None
        elif cumulative is not None:
            cumulative += remediation
            known_floor += remediation
        else:
            known_floor += remediation
        cumulative_weeks = None
        fits = None
        if cumulative is not None and weekly_hours is not None:
            cumulative_weeks = cumulative / weekly_hours
            fits = cumulative_weeks <= weeks_available
            if fits is False and first_past is None:
                first_past = entry["id"]
        schedule.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "requirement_level": entry["requirement_level"],
                "current_state": entry["current_state"],
                "evidence_artifact": entry["evidence_artifact"],
                "remediation_hours": _number(remediation),
                "cumulative_hours": _number(cumulative),
                "cumulative_weeks": _number(cumulative_weeks),
                "fits_before_deadline": fits,
                "owner": entry["owner"],
            }
        )

    incomplete_hours = any(entry["remediation_hours"] is None for entry in gaps)
    if incomplete_hours:
        warnings.append("remediation_hours_incomplete")
    total_hours = None if incomplete_hours else known_floor
    required_weeks = None if total_hours is None or weekly_hours is None else total_hours / weekly_hours
    feasible = None if required_weeks is None else required_weeks <= weeks_available

    covered: list[str] = []
    cost_total: Decimal | None = None
    if mode == "advanced":
        seen_controls: set[str] = set()
        known_ids = {entry["id"] for entry in items}
        for index, raw_control in enumerate(_list(data.get("compensating_controls", []), "compensating_controls")):
            path = f"compensating_controls[{index}]"
            control = _object(raw_control, path)
            item_id = _string(control.get("item_id"), f"{path}.item_id")
            if item_id not in known_ids:
                raise ValueError(f"{path}.item_id must reference a known item")
            if item_id in seen_controls:
                raise ValueError("compensating control item ids must be unique")
            seen_controls.add(item_id)
            _string(control.get("description"), f"{path}.description")
            accepted = control.get("accepted_by_customer")
            if accepted is None:
                unknowns.append(f"{path}.accepted_by_customer")
            elif not isinstance(accepted, bool):
                raise ValueError(f"{path}.accepted_by_customer must be true, false, or null")
            elif accepted and any(gap["id"] == item_id for gap in must_gaps):
                covered.append(item_id)
        gap_costs = [entry["remediation_cost"] for entry in gaps]
        if gap_costs and not any(cost is None for cost in gap_costs):
            cost_total = sum(gap_costs, Decimal(0))
        elif any(cost is None for cost in gap_costs):
            warnings.append("remediation_cost_incomplete")

    remaining = sorted(gap["id"] for gap in must_gaps if gap["id"] not in covered)

    if all(entry["current_state"] == "unknown" for entry in items):
        status = "indeterminate"
    elif unknowns or warnings:
        status = "partial"
    else:
        status = "complete"

    return {
        "as_of_date": as_of.isoformat(),
        "submission_deadline": deadline.isoformat(),
        "currency": currency,
        "totals": {
            "items": len(items),
            "answerable_now": sum(1 for entry in items if entry["answerable_now"]),
            "gaps": len(gaps),
            "must_items": sum(1 for entry in items if entry["requirement_level"] == "must"),
            "must_answerable_now": sum(1 for entry in items if entry["requirement_level"] == "must" and entry["answerable_now"]),
        },
        "category_coverage": category_coverage,
        "must_gaps": [
            {
                "id": entry["id"],
                "category": entry["category"],
                "current_state": entry["current_state"],
                "evidence_artifact": entry["evidence_artifact"],
            }
            for entry in must_gaps
        ],
        "must_gaps_covered_by_control": sorted(covered),
        "must_gaps_remaining": remaining,
        "schedule": schedule,
        "schedule_summary": {
            "weeks_available": _number(weeks_available),
            "remediation_hours_total": _number(total_hours),
            "remediation_hours_known_floor": _number(known_floor),
            "required_weeks": _number(required_weeks),
            "schedule_feasible": feasible,
            "first_item_past_deadline": first_past,
        },
        "remediation_cost_total": _number(cost_total),
        "readiness_scope": "evidence-backed answerability and deadline arithmetic only; control effectiveness, certification, contractual acceptance, and customer judgement remain separate",
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
        print("usage: assess_security_readiness.py <input.json>", file=sys.stderr)
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
