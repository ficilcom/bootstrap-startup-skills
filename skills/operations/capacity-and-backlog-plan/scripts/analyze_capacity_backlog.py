#!/usr/bin/env python3
"""Reconcile committed, backlog, and qualified demand with capacity."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
PERIOD_UNITS = {"week", "month", "quarter"}
COMMITMENTS = {"committed", "backlog", "qualified"}
INTERVENTION_TYPES = {"overtime", "outsource", "hire", "resequence"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


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


def _integer(value: object, path: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{path} must be an integer of at least {minimum}")
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


def _scalar(value: object, path: str) -> Decimal | None:
    return _evidenced(value, path, "value")


def _money(value: object, path: str, currency: str) -> Decimal | None:
    return _evidenced(value, path, "amount", currency)


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


def _sum_known(values: list[Decimal | None]) -> Decimal | None:
    return None if any(value is None for value in values) else sum(values, Decimal(0))


def _first_breach(demand: list[Decimal | None], capacity: list[Decimal | None]) -> tuple[int | None, Decimal | None]:
    cumulative_demand = Decimal(0)
    cumulative_capacity = Decimal(0)
    maximum_gap = Decimal(0)
    first: int | None = None
    determinate = True
    for index, (demand_value, capacity_value) in enumerate(zip(demand, capacity), start=1):
        if demand_value is None or capacity_value is None:
            determinate = False
            continue
        if not determinate:
            continue
        cumulative_demand += demand_value
        cumulative_capacity += capacity_value
        gap = max(Decimal(0), cumulative_demand - cumulative_capacity)
        maximum_gap = max(maximum_gap, gap)
        if gap > 0 and first is None:
            first = index
    return first, maximum_gap if determinate else None


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    period_unit = data.get("period_unit")
    if period_unit not in PERIOD_UNITS:
        raise ValueError("period_unit must be week, month, or quarter")
    horizon = _integer(data.get("horizon_periods"), "horizon_periods")

    capacity: list[Decimal | None] = [None] * horizon
    period_ids: set[int] = set()
    decision_unknowns: list[str] = []
    for index, raw_period in enumerate(_list(data.get("periods"), "periods", nonempty=True)):
        path = f"periods[{index}]"
        period = _object(raw_period, path)
        period_number = _integer(period.get("period"), f"{path}.period")
        if period_number > horizon:
            raise ValueError(f"{path}.period must be within horizon_periods")
        if period_number in period_ids:
            raise ValueError("period numbers must be unique")
        period_ids.add(period_number)
        internal = _scalar(period.get("internal_capacity_hours"), f"{path}.internal_capacity_hours")
        external = _scalar(period.get("external_capacity_hours"), f"{path}.external_capacity_hours")
        if internal is None:
            decision_unknowns.append(f"{path}.internal_capacity_hours")
        if external is None:
            decision_unknowns.append(f"{path}.external_capacity_hours")
        capacity[period_number - 1] = _sum_known([internal, external])
    if period_ids != set(range(1, horizon + 1)):
        raise ValueError("periods must contain each period in horizon exactly once")

    demand: dict[str, list[list[Decimal | None]]] = {kind: [[] for _ in range(horizon)] for kind in COMMITMENTS}
    item_records: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    contribution_order_parts: list[tuple[str, Decimal]] = []
    for index, raw_item in enumerate(_list(data.get("work_items"), "work_items", nonempty=True)):
        path = f"work_items[{index}]"
        item = _object(raw_item, path)
        item_id = _string(item.get("id"), f"{path}.id")
        if item_id in seen_items:
            raise ValueError("work item ids must be unique")
        seen_items.add(item_id)
        due_period = _integer(item.get("due_period"), f"{path}.due_period")
        if due_period > horizon:
            raise ValueError(f"{path}.due_period must be within horizon_periods")
        commitment = item.get("commitment")
        if commitment not in COMMITMENTS:
            raise ValueError(f"{path}.commitment must be committed, backlog, or qualified")
        hours = _scalar(item.get("required_hours"), f"{path}.required_hours")
        if hours is None:
            decision_unknowns.append(f"{path}.required_hours")
        raw_contribution = item.get("contribution")
        contribution = None if raw_contribution is None else _money(raw_contribution, f"{path}.contribution", currency)
        if hours is not None and hours > 0 and contribution is not None:
            contribution_order_parts.append((item_id, contribution / hours))
        demand[str(commitment)][due_period - 1].append(hours)
        item_records.append({"id": item_id, "due_period": due_period, "commitment": commitment})

    direct: dict[str, list[Decimal | None]] = {kind: [_sum_known(values) for values in periods] for kind, periods in demand.items()}
    delivery = [_sum_known([direct["committed"][index], direct["backlog"][index]]) for index in range(horizon)]
    potential = [_sum_known([delivery[index], direct["qualified"][index]]) for index in range(horizon)]
    first_delivery, maximum_delivery_gap = _first_breach(delivery, capacity)
    first_potential, _ = _first_breach(potential, capacity)

    period_metrics: list[dict[str, Any]] = []
    cumulative_delivery = Decimal(0)
    cumulative_capacity = Decimal(0)
    cumulative_known = True
    for index in range(horizon):
        if delivery[index] is None or capacity[index] is None:
            cumulative_known = False
        if cumulative_known:
            cumulative_delivery += delivery[index]
            cumulative_capacity += capacity[index]
            cumulative_gap = max(Decimal(0), cumulative_delivery - cumulative_capacity)
        else:
            cumulative_gap = None
        period_metrics.append({
            "period": index + 1,
            "capacity_hours": _number(capacity[index]),
            "committed_demand_hours": _number(direct["committed"][index]),
            "backlog_demand_hours": _number(direct["backlog"][index]),
            "qualified_demand_hours": _number(direct["qualified"][index]),
            "delivery_demand_hours": _number(delivery[index]),
            "potential_demand_hours": _number(potential[index]),
            "cumulative_delivery_gap_hours": _number(cumulative_gap),
        })

    if first_delivery is not None:
        acceptance_gate = "closed"
    elif maximum_delivery_gap is None:
        acceptance_gate = "indeterminate"
    elif first_potential is not None:
        acceptance_gate = "conditional"
    else:
        acceptance_gate = "open"
    at_risk = sorted(item["id"] for item in item_records if first_delivery is not None and item["commitment"] in {"committed", "backlog"} and item["due_period"] <= first_delivery)

    intervention_metrics: list[dict[str, Any]] = []
    scenario_metrics: list[dict[str, Any]] = []
    if mode == "advanced":
        intervention_ids: set[str] = set()
        for index, raw_intervention in enumerate(_list(data.get("interventions", []), "interventions")):
            path = f"interventions[{index}]"
            intervention = _object(raw_intervention, path)
            intervention_id = _string(intervention.get("id"), f"{path}.id")
            if intervention_id in intervention_ids:
                raise ValueError("intervention ids must be unique")
            intervention_ids.add(intervention_id)
            intervention_type = intervention.get("type")
            if intervention_type not in INTERVENTION_TYPES:
                raise ValueError(f"{path}.type must be supported")
            start = _integer(intervention.get("start_period"), f"{path}.start_period")
            if start > horizon:
                raise ValueError(f"{path}.start_period must be within horizon_periods")
            added = _scalar(intervention.get("capacity_hours_per_period"), f"{path}.capacity_hours_per_period")
            one_time = _money(intervention.get("one_time_cost"), f"{path}.one_time_cost", currency)
            recurring = _money(intervention.get("recurring_cost_per_period"), f"{path}.recurring_cost_per_period", currency)
            for field, value in (("capacity_hours_per_period", added), ("one_time_cost", one_time), ("recurring_cost_per_period", recurring)):
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            active_periods = horizon - start + 1
            total_added = None if added is None else added * active_periods
            total_cost = None if one_time is None or recurring is None else one_time + recurring * active_periods
            adjusted_capacity = [None if value is None or (period >= start and added is None) else value + (added if period >= start else Decimal(0)) for period, value in enumerate(capacity, start=1)]
            intervention_breach, intervention_gap = _first_breach(delivery, adjusted_capacity)
            intervention_metrics.append({"id": intervention_id, "type": intervention_type, "total_added_capacity_hours": _number(total_added), "total_cost": _number(total_cost), "first_delivery_breach_period": intervention_breach, "maximum_cumulative_delivery_gap_hours": _number(intervention_gap)})

        scenario_ids: set[str] = set()
        for index, raw_scenario in enumerate(_list(data.get("scenarios", []), "scenarios")):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            scenario_id = _string(scenario.get("id"), f"{path}.id")
            if scenario_id in scenario_ids:
                raise ValueError("scenario ids must be unique")
            scenario_ids.add(scenario_id)
            demand_factor = _scalar(scenario.get("demand_factor"), f"{path}.demand_factor")
            capacity_factor = _scalar(scenario.get("capacity_factor"), f"{path}.capacity_factor")
            if demand_factor is None:
                decision_unknowns.append(f"{path}.demand_factor")
            if capacity_factor is None:
                decision_unknowns.append(f"{path}.capacity_factor")
            scenario_demand = [None if value is None or demand_factor is None else value * demand_factor for value in delivery]
            scenario_capacity = [None if value is None or capacity_factor is None else value * capacity_factor for value in capacity]
            scenario_breach, scenario_gap = _first_breach(scenario_demand, scenario_capacity)
            scenario_metrics.append({"id": scenario_id, "first_delivery_breach_period": scenario_breach, "maximum_cumulative_delivery_gap_hours": _number(scenario_gap)})

    contribution_order_parts.sort(key=lambda item: (-item[1], item[0]))
    unknowns = sorted(set(decision_unknowns))
    quality_status = "partial" if unknowns and maximum_delivery_gap is not None else "indeterminate" if maximum_delivery_gap is None else "complete"
    warnings = []
    if first_delivery is not None:
        warnings.append("delivery_capacity_breach")
    if first_potential is not None:
        warnings.append("potential_capacity_breach")
    return {
        "currency": currency,
        "period_unit": period_unit,
        "horizon_periods": horizon,
        "period_metrics": period_metrics,
        "first_delivery_breach_period": first_delivery,
        "first_potential_breach_period": first_potential,
        "maximum_cumulative_delivery_gap_hours": _number(maximum_delivery_gap),
        "acceptance_gate": acceptance_gate,
        "at_risk_items": at_risk,
        "contribution_per_hour_order": [item[0] for item in contribution_order_parts],
        "ranking_scope": "known contribution per required hour only; commitment, due date, quality, customer, people, and contract gates remain separate",
        "intervention_metrics": intervention_metrics,
        "scenario_metrics": scenario_metrics,
        "analysis_quality": {"mode": mode, "status": quality_status, "evidence_counts": _evidence_counts(data), "decision_changing_unknowns": unknowns, "warnings": warnings},
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_capacity_backlog.py <input.json>", file=sys.stderr)
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
