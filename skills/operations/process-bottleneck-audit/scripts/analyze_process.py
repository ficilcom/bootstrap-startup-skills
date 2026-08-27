#!/usr/bin/env python3
"""Calculate comparable process capacity, flow, WIP, and bottleneck signals."""

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
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
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


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    process_name = _string(data.get("process_name"), "process_name")
    period_label = _string(data.get("period_label"), "period_label")
    demand = _scalar(data.get("demand_units"), "demand_units")
    missing: list[str] = []
    if demand is None:
        missing.append("demand_units")

    seen: set[str] = set()
    step_results: list[dict[str, Any]] = []
    sort_values: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    for index, raw_step in enumerate(_list(data.get("steps"), "steps")):
        path = f"steps[{index}]"
        step = _object(raw_step, path)
        name = _string(step.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("step names must be unique")
        seen.add(name)

        fields = {
            field: _scalar(step.get(field), f"{path}.{field}")
            for field in (
                "opening_wip_units",
                "arrived_units",
                "completed_units",
                "available_minutes",
                "work_minutes_per_unit",
                "wait_time_hours",
                "rework_units",
                "blocked_units",
            )
        }
        for field, value in fields.items():
            if value is None:
                missing.append(f"{path}.{field}")
        work_time = fields["work_minutes_per_unit"]
        if work_time == 0:
            raise ValueError(f"{path}.work_minutes_per_unit must be greater than zero")

        complete = all(value is not None for value in fields.values()) and demand is not None
        capacity = utilization = closing_wip = backlog_periods = first_pass_yield = shortfall = None
        flags: list[str] = []
        if complete:
            opening = fields["opening_wip_units"]
            arrived = fields["arrived_units"]
            completed = fields["completed_units"]
            available = fields["available_minutes"]
            wait = fields["wait_time_hours"]
            rework = fields["rework_units"]
            blocked = fields["blocked_units"]
            assert None not in (opening, arrived, completed, available, work_time, wait, rework, blocked, demand)
            assert opening is not None and arrived is not None and completed is not None
            assert available is not None and work_time is not None and wait is not None
            assert rework is not None and blocked is not None and demand is not None
            if completed > opening + arrived:
                raise ValueError(f"{path}.completed_units cannot exceed available units")
            closing_wip = opening + arrived - completed
            if rework > completed:
                raise ValueError(f"{path}.rework_units cannot exceed completed_units")
            if blocked > closing_wip:
                raise ValueError(f"{path}.blocked_units cannot exceed closing WIP")
            capacity = available / work_time
            utilization = completed / capacity if capacity else None
            shortfall = max(demand - capacity, Decimal(0))
            backlog_periods = closing_wip / completed if completed else None
            first_pass_yield = (completed - rework) / completed if completed else None
            if completed == 0:
                flags.append("zero_throughput")
            if utilization is not None and utilization > 1:
                flags.append("completed_above_modeled_capacity")
            if blocked > 0:
                flags.append("blocked_work")
            sort_values[name] = (shortfall, closing_wip, wait, utilization or Decimal(0))

        step_results.append(
            {
                "name": name,
                "status": "complete" if complete else "indeterminate",
                "capacity_units": _number(capacity),
                "capacity_shortfall_vs_demand": _number(shortfall),
                "utilization": _number(utilization),
                "closing_wip_units": _number(closing_wip),
                "backlog_periods_at_current_throughput": _number(backlog_periods),
                "first_pass_yield": _number(first_pass_yield),
                "wait_time_hours": _number(fields["wait_time_hours"]),
                "blocked_units": _number(fields["blocked_units"]),
                "flags": flags,
            }
        )

    candidates = sorted(
        sort_values,
        key=lambda name: tuple(-value for value in sort_values[name]) + (name,),
    )
    final_throughput = None
    if step_results and step_results[-1]["status"] == "complete":
        last_raw = _object(_list(data.get("steps"), "steps")[-1], "last step")
        final_throughput = _scalar(last_raw.get("completed_units"), "last step.completed_units")
    demand_gap = max(demand - final_throughput, Decimal(0)) if demand is not None and final_throughput is not None else None

    return {
        "process_name": process_name,
        "period_label": period_label,
        "steps": step_results,
        "final_throughput_units": _number(final_throughput),
        "demand_gap_units": _number(demand_gap),
        "constraint_candidates": candidates,
        "candidate_order_scope": "known capacity shortfall, closing WIP, wait, then utilization",
        "missing_inputs": sorted(set(missing)),
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_process.py <input.json>", file=sys.stderr)
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
