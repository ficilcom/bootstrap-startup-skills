#!/usr/bin/env python3
"""Analyze founder time by value, leverage, necessity, and delegation readiness."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}


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


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
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
        activities.append({
            "name": name,
            "hours": _number(hours),
            "time_share": _number(share),
            "focus_score": focus_score,
            "flags": flags,
        })

    if available is None:
        missing.append("available_hours")
    status = "complete" if all_hours_known else "indeterminate"
    allocated = known_total if all_hours_known else None
    unallocated = max(Decimal(0), available - known_total) if all_hours_known and available is not None else None
    overallocated = max(Decimal(0), known_total - available) if all_hours_known and available is not None else None
    return {
        "review_period": period,
        "activities": activities,
        "summary": {
            "status": status,
            "allocated_hours": _number(allocated),
            "unallocated_hours": _number(unallocated),
            "overallocated_hours": _number(overallocated),
            "reclaimable_hours": _number(reclaimable) if all_hours_known else None,
        },
        "protect_candidates": [name for _, name in sorted(protect)],
        "delegate_candidates": [name for _, name in sorted(delegate)],
        "eliminate_or_reduce_candidates": [name for _, name in sorted(eliminate)],
        "missing_inputs": sorted(set(missing)),
        "scope": "descriptive candidates only; delegation, cancellation, and calendar changes require human approval",
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
