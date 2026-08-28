#!/usr/bin/env python3
"""Build an annual operating plan cash path and test it against user-supplied targets."""

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
CHECKPOINT_METRICS = {"revenue", "gross_profit", "ending_cash"}
TARGET_KEYS = ("revenue", "gross_profit", "ending_cash")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
MONTHS = 12
QUARTER_MONTHS = 3


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


def _decimal(value: object, path: str, *, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{path} must be numeric") from error
    if not result.is_finite() or (result < 0 and not allow_negative):
        raise ValueError(f"{path} must be {'finite' if allow_negative else 'non-negative'}")
    return result


def _evidenced(
    value: object,
    path: str,
    field: str,
    currency: str | None = None,
    *,
    allow_negative: bool = False,
) -> Decimal | None:
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
    return _decimal(raw, f"{path}.{field}", allow_negative=allow_negative)


def _money(value: object, path: str, currency: str) -> Decimal | None:
    return _evidenced(value, path, "amount", currency)


def _rate(value: object, path: str, *, low: Decimal, high: Decimal) -> Decimal | None:
    result = _evidenced(value, path, "value", allow_negative=low < 0)
    if result is not None and not low <= result <= high:
        raise ValueError(f"{path} must be between {low} and {high}")
    return result


def _money_series(value: object, path: str, currency: str, unknowns: list[str]) -> list[Decimal | None]:
    values = _list(value, path)
    if len(values) != MONTHS:
        raise ValueError(f"{path} must contain 12 entries")
    result: list[Decimal | None] = []
    for index, item in enumerate(values):
        amount = _money(item, f"{path}[{index}]", currency)
        if amount is None:
            unknowns.append(f"{path}[{index}]")
        result.append(amount)
    return result


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


def _total(values: list[Decimal | None]) -> Decimal | None:
    if any(value is None for value in values):
        return None
    return sum(values, Decimal(0))


def _cash_path(
    opening: Decimal | None,
    buffer_amount: Decimal | None,
    net_cash: list[Decimal | None],
) -> tuple[list[Decimal | None], Decimal | None, int | None, int | None]:
    ending: list[Decimal | None] = [None] * MONTHS
    if opening is None:
        return ending, None, None, 1
    cash = opening
    truncated_at = None
    for month in range(1, MONTHS + 1):
        flow = net_cash[month - 1]
        if flow is None:
            truncated_at = month
            break
        cash += flow
        ending[month - 1] = cash
    known = [value for value in ending if value is not None]
    minimum = min(known) if known else None
    breach = None
    if buffer_amount is not None:
        for month, value in enumerate(ending, start=1):
            if value is not None and value < buffer_amount:
                breach = month
                break
    return ending, minimum, breach, truncated_at


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    fiscal_year_start = _date(data.get("fiscal_year_start"), "fiscal_year_start")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    unknowns: list[str] = []
    warnings: list[str] = []

    opening = _money(data.get("opening_cash"), "opening_cash", currency)
    if opening is None:
        unknowns.append("opening_cash")
    buffer_amount = _money(data.get("minimum_cash_buffer"), "minimum_cash_buffer", currency)
    if buffer_amount is None:
        unknowns.append("minimum_cash_buffer")

    streams: list[dict[str, Any]] = []
    stream_ids: set[str] = set()
    for index, raw_stream in enumerate(_list(data.get("revenue_streams"), "revenue_streams")):
        path = f"revenue_streams[{index}]"
        stream = _object(raw_stream, path)
        stream_id = _string(stream.get("id"), f"{path}.id")
        if stream_id in stream_ids:
            raise ValueError("revenue stream ids must be unique")
        stream_ids.add(stream_id)
        monthly = _money_series(stream.get("monthly_revenue"), f"{path}.monthly_revenue", currency, unknowns)
        rate = _rate(stream.get("gross_margin_rate"), f"{path}.gross_margin_rate", low=Decimal(0), high=Decimal(1))
        if rate is None:
            unknowns.append(f"{path}.gross_margin_rate")
        streams.append({"id": stream_id, "monthly_revenue": monthly, "gross_margin_rate": rate})
    if not streams:
        raise ValueError("revenue_streams must contain at least one stream")

    fixed_costs = _money_series(data.get("fixed_costs_by_month"), "fixed_costs_by_month", currency, unknowns)

    committed: list[Decimal | None] = [Decimal(0)] * MONTHS
    for index, raw_outflow in enumerate(_list(data.get("committed_outflows", []), "committed_outflows")):
        path = f"committed_outflows[{index}]"
        outflow = _object(raw_outflow, path)
        _string(outflow.get("name"), f"{path}.name")
        month_index = outflow.get("month_index")
        if isinstance(month_index, bool) or not isinstance(month_index, int) or not 1 <= month_index <= MONTHS:
            raise ValueError(f"{path}.month_index must be an integer between 1 and 12")
        amount = _money(outflow.get("amount"), f"{path}.amount", currency)
        if amount is None:
            unknowns.append(f"{path}.amount")
            committed[month_index - 1] = None
        elif committed[month_index - 1] is not None:
            committed[month_index - 1] += amount

    revenue_by_month = [_total([stream["monthly_revenue"][month] for stream in streams]) for month in range(MONTHS)]
    gross_profit_by_month: list[Decimal | None] = []
    for month in range(MONTHS):
        parts = [
            None if stream["monthly_revenue"][month] is None or stream["gross_margin_rate"] is None
            else stream["monthly_revenue"][month] * stream["gross_margin_rate"]
            for stream in streams
        ]
        gross_profit_by_month.append(_total(parts))
    net_cash_by_month = [_total([gross_profit_by_month[month], -fixed_costs[month] if fixed_costs[month] is not None else None, -committed[month] if committed[month] is not None else None]) for month in range(MONTHS)]

    ending, minimum_cash, breach_month, truncated_at = _cash_path(opening, buffer_amount, net_cash_by_month)
    if truncated_at is not None:
        warnings.append(f"cash_path_truncated_at_month_{truncated_at}")

    quarters: list[dict[str, Any]] = []
    for quarter in range(1, MONTHS // QUARTER_MONTHS + 1):
        window = range((quarter - 1) * QUARTER_MONTHS, quarter * QUARTER_MONTHS)
        quarters.append(
            {
                "quarter": quarter,
                "revenue": _number(_total([revenue_by_month[month] for month in window])),
                "gross_profit": _number(_total([gross_profit_by_month[month] for month in window])),
                "net_cash": _number(_total([net_cash_by_month[month] for month in window])),
                "ending_cash": _number(ending[quarter * QUARTER_MONTHS - 1]),
            }
        )

    annual_revenue = _total(revenue_by_month)
    annual_gross_profit = _total(gross_profit_by_month)
    annual_ending_cash = ending[MONTHS - 1]
    planned = {"revenue": annual_revenue, "gross_profit": annual_gross_profit, "ending_cash": annual_ending_cash}

    raw_targets = _object(data.get("annual_targets", {}), "annual_targets")
    target_assessment: dict[str, Any] = {}
    targets: dict[str, Decimal | None] = {}
    for key in TARGET_KEYS:
        raw = raw_targets.get(key)
        target = None if raw is None else _money(raw, f"annual_targets.{key}", currency)
        targets[key] = target
        if target is None:
            unknowns.append(f"annual_targets.{key}")
        actual = planned[key]
        reaches = None if target is None or actual is None else actual >= target
        shortfall = None if target is None or actual is None else max(Decimal(0), target - actual)
        target_assessment[key] = {
            "target": _number(target),
            "planned": _number(actual),
            "reaches_target": reaches,
            "shortfall": _number(shortfall),
        }

    required_gross_profit = None
    if targets["ending_cash"] is not None and annual_ending_cash is not None:
        required_gross_profit = max(Decimal(0), targets["ending_cash"] - annual_ending_cash)

    scenarios: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_ids: set[str] = set()
        for index, raw_scenario in enumerate(_list(data.get("scenarios", []), "scenarios")):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            scenario_id = _string(scenario.get("id"), f"{path}.id")
            if scenario_id in scenario_ids:
                raise ValueError("scenario ids must be unique")
            scenario_ids.add(scenario_id)
            revenue_multiplier = _rate(scenario.get("revenue_multiplier"), f"{path}.revenue_multiplier", low=Decimal(0), high=Decimal(10))
            margin_delta = _rate(scenario.get("margin_delta"), f"{path}.margin_delta", low=Decimal(-1), high=Decimal(1))
            cost_multiplier = _rate(scenario.get("cost_multiplier"), f"{path}.cost_multiplier", low=Decimal(0), high=Decimal(10))
            for name, value in (("revenue_multiplier", revenue_multiplier), ("margin_delta", margin_delta), ("cost_multiplier", cost_multiplier)):
                if value is None:
                    unknowns.append(f"{path}.{name}")
            scenario_revenue: list[Decimal | None] = []
            scenario_gross: list[Decimal | None] = []
            for month in range(MONTHS):
                revenue_parts = [
                    None if stream["monthly_revenue"][month] is None or revenue_multiplier is None
                    else stream["monthly_revenue"][month] * revenue_multiplier
                    for stream in streams
                ]
                gross_parts = []
                for stream, revenue_part in zip(streams, revenue_parts):
                    if revenue_part is None or stream["gross_margin_rate"] is None or margin_delta is None:
                        gross_parts.append(None)
                        continue
                    effective = stream["gross_margin_rate"] + margin_delta
                    if effective < 0:
                        warnings.append(f"{scenario_id}:negative_effective_margin")
                    gross_parts.append(revenue_part * effective)
                scenario_revenue.append(_total(revenue_parts))
                scenario_gross.append(_total(gross_parts))
            scenario_net = [
                _total(
                    [
                        scenario_gross[month],
                        None if fixed_costs[month] is None or cost_multiplier is None else -(fixed_costs[month] * cost_multiplier),
                        None if committed[month] is None else -committed[month],
                    ]
                )
                for month in range(MONTHS)
            ]
            scenario_ending, scenario_minimum, scenario_breach, scenario_truncated = _cash_path(opening, buffer_amount, scenario_net)
            if scenario_truncated is not None:
                warnings.append(f"{scenario_id}:cash_path_truncated_at_month_{scenario_truncated}")
            scenarios.append(
                {
                    "id": scenario_id,
                    "annual_revenue": _number(_total(scenario_revenue)),
                    "annual_gross_profit": _number(_total(scenario_gross)),
                    "ending_cash": _number(scenario_ending[MONTHS - 1]),
                    "minimum_cash": _number(scenario_minimum),
                    "buffer_breach_month": scenario_breach,
                    "status": "complete" if scenario_ending[MONTHS - 1] is not None else "indeterminate",
                }
            )

        seen_checkpoints: set[tuple[int, str]] = set()
        quarter_lookup = {item["quarter"]: item for item in quarters}
        for index, raw_checkpoint in enumerate(_list(data.get("quarterly_checkpoints", []), "quarterly_checkpoints")):
            path = f"quarterly_checkpoints[{index}]"
            checkpoint = _object(raw_checkpoint, path)
            quarter = checkpoint.get("quarter")
            if isinstance(quarter, bool) or not isinstance(quarter, int) or not 1 <= quarter <= MONTHS // QUARTER_MONTHS:
                raise ValueError(f"{path}.quarter must be an integer between 1 and 4")
            metric = checkpoint.get("metric")
            if metric not in CHECKPOINT_METRICS:
                raise ValueError(f"{path}.metric must be revenue, gross_profit, or ending_cash")
            if (quarter, metric) in seen_checkpoints:
                raise ValueError("checkpoint quarter and metric pairs must be unique")
            seen_checkpoints.add((quarter, metric))
            threshold = _money(checkpoint.get("threshold"), f"{path}.threshold", currency)
            if threshold is None:
                unknowns.append(f"{path}.threshold")
            revision_trigger = _string(checkpoint.get("revision_trigger"), f"{path}.revision_trigger")
            planned_value = quarter_lookup[quarter][metric]
            meets = None if threshold is None or planned_value is None else Decimal(str(planned_value)) >= threshold
            checkpoints.append(
                {
                    "quarter": quarter,
                    "metric": metric,
                    "threshold": _number(threshold),
                    "planned_value": planned_value,
                    "meets_threshold": meets,
                    "revision_trigger": revision_trigger,
                }
            )

    headline = [annual_revenue, annual_gross_profit, annual_ending_cash, minimum_cash]
    if all(value is None for value in headline):
        status = "indeterminate"
    elif unknowns or warnings:
        status = "partial"
    else:
        status = "complete"

    return {
        "fiscal_year_start": fiscal_year_start.isoformat(),
        "currency": currency,
        "monthly": {
            "revenue": [_number(value) for value in revenue_by_month],
            "gross_profit": [_number(value) for value in gross_profit_by_month],
            "net_cash": [_number(value) for value in net_cash_by_month],
        },
        "cash_path": {
            "monthly_ending_cash": [_number(value) for value in ending],
            "minimum_cash": _number(minimum_cash),
            "buffer_breach_month": breach_month,
        },
        "quarters": quarters,
        "annual": {
            "revenue": _number(annual_revenue),
            "gross_profit": _number(annual_gross_profit),
            "ending_cash": _number(annual_ending_cash),
        },
        "target_assessment": target_assessment,
        "required_additional_gross_profit": _number(required_gross_profit),
        "scenarios": scenarios,
        "checkpoints": checkpoints,
        "planning_scope": "arithmetic reach of user-supplied assumptions and cash survivability only; target achievability, demand, capacity, and execution remain separate",
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
        print("usage: build_annual_plan.py <input.json>", file=sys.stderr)
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
