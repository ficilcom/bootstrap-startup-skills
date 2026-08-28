#!/usr/bin/env python3
"""Analyze founder time by value, leverage, necessity, and delegation readiness."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
READINESS_STATES = {"ready", "partial", "missing", "unknown"}


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


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


def _scalar(value: object, path: str) -> Decimal | None:
    item = _object(value, path)
    evidence = item.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be supported")
    raw = item.get("value")
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path}.value must be null when evidence is unknown")
        return None
    if raw is None:
        raise ValueError(f"{path}.value is required unless evidence is unknown")
    return _decimal(raw, f"{path}.value")


def _score(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        raise ValueError(f"{path} must be an integer between 0 and 5")
    return value


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


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


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
    period = _string(data.get("review_period"), "review_period")
    available = _scalar(data.get("available_hours"), "available_hours")
    if available is not None and available <= 0:
        raise ValueError("available_hours must be greater than zero")

    seen: set[str] = set()
    missing: list[str] = []
    activities: list[dict[str, Any]] = []
    known_total = Decimal(0)
    all_hours_known = available is not None
    protect: list[tuple[int, str]] = []
    delegate: list[tuple[Decimal, str]] = []
    eliminate: list[tuple[Decimal, str]] = []
    reclaimable = Decimal(0)
    decision_unknowns: list[str] = []
    observed_weeks = _positive_integer(data.get("observed_weeks"), "observed_weeks") if mode == "advanced" else 1
    planning_horizon = _positive_integer(data.get("planning_horizon_weeks"), "planning_horizon_weeks") if mode == "advanced" else 1
    fragmentation_threshold = _scalar(data.get("fragmentation_threshold_per_week"), "fragmentation_threshold_per_week") if mode == "advanced" else None
    if mode == "advanced" and (fragmentation_threshold is None or fragmentation_threshold <= 0):
        raise ValueError("fragmentation_threshold_per_week must be greater than zero")
    advanced_gross_total = Decimal(0)
    advanced_net_total = Decimal(0)

    for index, raw_activity in enumerate(_list(data.get("activities"), "activities")):
        path = f"activities[{index}]"
        item = _object(raw_activity, path)
        name = _string(item.get("name"), f"{path}.name")
        _string(item.get("category"), f"{path}.category")
        if name in seen:
            raise ValueError("activity names must be unique")
        seen.add(name)
        hours = _scalar(item.get("hours"), f"{path}.hours")
        required = item.get("founder_required")
        if not isinstance(required, bool):
            raise ValueError(f"{path}.founder_required must be boolean")
        value = _score(item.get("value_score"), f"{path}.value_score")
        leverage = _score(item.get("leverage_score"), f"{path}.leverage_score")
        readiness = _score(item.get("delegation_readiness"), f"{path}.delegation_readiness")
        focus_score = value * leverage
        share = hours / available if hours is not None and available is not None else None
        flags: list[str] = []
        if hours is None:
            all_hours_known = False
            missing.append(f"{path}.hours")
        else:
            known_total += hours
        if required or focus_score >= 16:
            protect.append((-focus_score, name))
            flags.append("protect_focus")
        elif readiness >= 3:
            delegate.append((-(hours or Decimal(0)), name))
            flags.append("delegation_candidate")
            if hours is not None:
                reclaimable += hours
        elif value <= 1 and leverage <= 1:
            eliminate.append((-(hours or Decimal(0)), name))
            flags.append("eliminate_or_reduce_candidate")
            if hours is not None:
                reclaimable += hours
        advanced: dict[str, Any] = {}
        if mode == "advanced":
            frequency = _scalar(item.get("frequency_per_week"), f"{path}.frequency_per_week")
            context_switches = _scalar(item.get("context_switches"), f"{path}.context_switches")
            _string(item.get("outcome_metric"), f"{path}.outcome_metric")
            transfer = _object(item.get("transfer"), f"{path}.transfer")
            transferable_rate = _scalar(transfer.get("transferable_rate"), f"{path}.transfer.transferable_rate")
            if transferable_rate is not None and transferable_rate > 1:
                raise ValueError(f"{path}.transfer.transferable_rate must be between 0 and 1")
            initial_transition = _scalar(transfer.get("initial_transition_hours"), f"{path}.transfer.initial_transition_hours")
            weekly_oversight = _scalar(transfer.get("weekly_oversight_hours"), f"{path}.transfer.weekly_oversight_hours")
            recipient_capacity = _scalar(transfer.get("recipient_capacity_hours"), f"{path}.transfer.recipient_capacity_hours")
            readiness: dict[str, str] = {}
            for field in ("procedure_status", "quality_status", "authority_status"):
                status_value = transfer.get(field)
                if status_value not in READINESS_STATES:
                    raise ValueError(f"{path}.transfer.{field} must be supported")
                readiness[field] = str(status_value)
            values = {
                "frequency_per_week": frequency,
                "context_switches": context_switches,
                "transferable_rate": transferable_rate,
                "initial_transition_hours": initial_transition,
                "weekly_oversight_hours": weekly_oversight,
                "recipient_capacity_hours": recipient_capacity,
            }
            for field, value in values.items():
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            weekly_hours = hours / observed_weeks if hours is not None else None
            switches_per_week = context_switches / observed_weeks if context_switches is not None else None
            gross_weekly = weekly_hours * transferable_rate if weekly_hours is not None and transferable_rate is not None else None
            gross_horizon = gross_weekly * planning_horizon if gross_weekly is not None else None
            net_horizon = gross_horizon - initial_transition - weekly_oversight * planning_horizon if gross_horizon is not None and initial_transition is not None and weekly_oversight is not None else None
            net_weekly = gross_weekly - weekly_oversight if gross_weekly is not None and weekly_oversight is not None else None
            payback = initial_transition / net_weekly if initial_transition is not None and net_weekly is not None and net_weekly > 0 else None
            capacity_gap = max(Decimal(0), gross_weekly - recipient_capacity) if gross_weekly is not None and recipient_capacity is not None else None
            gates: list[str] = []
            if required:
                gates.append("founder_required")
            if capacity_gap is not None and capacity_gap > 0:
                gates.append("recipient_capacity_shortfall")
            for field, status_value in readiness.items():
                if status_value != "ready":
                    gates.append(field)
                    if status_value == "unknown":
                        decision_unknowns.append(f"{path}.transfer.{field}")
            if gates:
                transition_status = "blocked"
            elif net_horizon is None:
                transition_status = "indeterminate"
            elif net_horizon <= 0:
                transition_status = "uneconomic"
            else:
                transition_status = "viable"
            if focus_score >= 16 and switches_per_week is not None and fragmentation_threshold is not None and switches_per_week > fragmentation_threshold:
                flags.append("focus_fragmentation")
            if transition_status == "uneconomic":
                flags.append("transition_not_economic")
            if capacity_gap is not None and capacity_gap > 0:
                flags.append("recipient_capacity_shortfall")
            if gross_horizon is not None:
                advanced_gross_total += gross_horizon
            if net_horizon is not None:
                advanced_net_total += net_horizon
            advanced = {
                "weekly_hours": _number(weekly_hours),
                "frequency_per_week": _number(frequency),
                "context_switches_per_week": _number(switches_per_week),
                "transition_gates": gates,
                "transition_economics": {
                    "status": transition_status,
                    "gross_reclaimable_hours": _number(gross_horizon),
                    "net_reclaimable_hours": _number(net_horizon),
                    "payback_weeks": _number(payback),
                    "recipient_capacity_gap_hours": _number(capacity_gap),
                },
            }
        activities.append({
            "name": name,
            "hours": _number(hours),
            "time_share": _number(share),
            "focus_score": focus_score,
            "flags": flags,
            **advanced,
        })

    if available is None:
        missing.append("available_hours")
    status = "complete" if all_hours_known else "indeterminate"
    allocated = known_total if all_hours_known else None
    unallocated = max(Decimal(0), available - known_total) if all_hours_known and available is not None else None
    overallocated = max(Decimal(0), known_total - available) if all_hours_known and available is not None else None
    if status == "indeterminate":
        quality_status = "indeterminate"
    elif decision_unknowns:
        quality_status = "partial"
    else:
        quality_status = "complete"
    return {
        "review_period": period,
        "activities": activities,
        "summary": {
            "status": status,
            "allocated_hours": _number(allocated),
            "unallocated_hours": _number(unallocated),
            "overallocated_hours": _number(overallocated),
            "reclaimable_hours": _number(reclaimable) if all_hours_known else None,
            "gross_reclaimable_hours": _number(advanced_gross_total) if mode == "advanced" else None,
            "net_reclaimable_hours": _number(advanced_net_total) if mode == "advanced" else None,
        },
        "protect_candidates": [name for _, name in sorted(protect)],
        "delegate_candidates": [name for _, name in sorted(delegate)],
        "eliminate_or_reduce_candidates": [name for _, name in sorted(eliminate)],
        "missing_inputs": sorted(set(missing)),
        "scope": "descriptive candidates only; delegation, cancellation, and calendar changes require human approval",
        "analysis_quality": {
            "mode": mode,
            "status": quality_status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": sorted(set(decision_unknowns)),
            "warnings": sorted({flag for activity in activities for flag in activity["flags"]}),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_founder_time.py <input.json>", file=sys.stderr)
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
