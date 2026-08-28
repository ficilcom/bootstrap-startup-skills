#!/usr/bin/env python3
"""Analyze offer-level contribution, delivery capacity, and strategic-fit signals."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
ANALYSIS_MODES = {"core", "advanced"}
RELATIONSHIP_TYPES = {"bundle", "cross_sell", "cannibalization", "shared_capacity"}


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


def _rate(value: object, path: str) -> Decimal:
    result = _decimal(value, path)
    if result > 1:
        raise ValueError(f"{path} must be between 0 and 1")
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


def _iso_date(value: object, path: str) -> date:
    text = _string(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


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
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    period = _string(data.get("period"), "period")
    available = _scalar(data.get("available_delivery_hours"), "available_delivery_hours")
    thresholds = _object(data.get("thresholds"), "thresholds")
    minimum_margin = _rate(thresholds.get("minimum_margin_rate"), "thresholds.minimum_margin_rate")
    heavy_share = _rate(thresholds.get("capacity_heavy_share"), "thresholds.capacity_heavy_share")

    seen: set[str] = set()
    missing: list[str] = []
    results: list[dict[str, Any]] = []
    total_revenue = Decimal(0)
    total_contribution = Decimal(0)
    total_hours = Decimal(0)
    portfolio_complete = available is not None
    decision_unknowns: list[str] = []
    components: dict[str, dict[str, Decimal | None]] = {}
    as_of = _iso_date(data.get("as_of_date"), "as_of_date") if mode == "advanced" else None

    for index, raw_offer in enumerate(_list(data.get("offers"), "offers")):
        path = f"offers[{index}]"
        offer = _object(raw_offer, path)
        name = _string(offer.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("offer names must be unique")
        seen.add(name)
        revenue = _money(offer.get("revenue"), f"{path}.revenue", currency)
        variable_cost = _money(offer.get("variable_cost"), f"{path}.variable_cost", currency)
        hours = _scalar(offer.get("delivery_hours"), f"{path}.delivery_hours")
        fit = _scalar(offer.get("strategic_fit"), f"{path}.strategic_fit")
        if fit is not None and fit > 5:
            raise ValueError(f"{path}.strategic_fit must be between 0 and 5")
        for field, value in (("revenue", revenue), ("variable_cost", variable_cost), ("delivery_hours", hours)):
            if value is None:
                missing.append(f"{path}.{field}")
        if fit is None:
            missing.append(f"{path}.strategic_fit")

        complete = all(value is not None for value in (revenue, variable_cost, hours))
        contribution = margin = per_hour = capacity_share = None
        flags: list[str] = []
        if complete:
            assert revenue is not None and variable_cost is not None and hours is not None
            contribution = revenue - variable_cost
            margin = contribution / revenue if revenue > 0 else None
            per_hour = contribution / hours if hours > 0 else None
            capacity_share = hours / available if available is not None and available > 0 else None
            total_revenue += revenue
            total_contribution += contribution
            total_hours += hours
            if contribution < 0:
                flags.append("negative_contribution")
            if margin is not None and margin < minimum_margin:
                flags.append("below_minimum_margin")
            if hours == 0:
                flags.append("zero_delivery_hours")
            if capacity_share is not None and capacity_share > heavy_share:
                flags.append("capacity_heavy")
        else:
            portfolio_complete = False
        if fit is not None and fit <= 1:
            flags.append("low_strategic_fit")

        advanced: dict[str, Any] = {}
        if mode == "advanced":
            demand = _object(offer.get("demand"), f"{path}.demand")
            demand_values: dict[str, Decimal | None] = {}
            for field in ("qualified_pipeline", "backlog_units", "lost_due_capacity_units", "renewal_rate"):
                raw_value = demand.get(field)
                if raw_value is None:
                    value = None
                elif field == "qualified_pipeline":
                    value = _money(raw_value, f"{path}.demand.{field}", currency)
                else:
                    value = _scalar(raw_value, f"{path}.demand.{field}")
                if field == "renewal_rate" and value is not None and value > 1:
                    raise ValueError(f"{path}.demand.renewal_rate must be between 0 and 1")
                demand_values[field] = value
            major_demand = [demand_values[field] for field in ("qualified_pipeline", "backlog_units", "renewal_rate")]
            if all(value is None for value in major_demand):
                demand_status = "unknown"
            elif all(value is not None for value in major_demand):
                demand_status = "confirmed"
            else:
                demand_status = "partial"
            if demand_status != "confirmed":
                for field in ("qualified_pipeline", "backlog_units", "renewal_rate"):
                    if demand_values[field] is None:
                        decision_unknowns.append(f"{path}.demand.{field}")

            exit_constraints = _object(offer.get("exit_constraints"), f"{path}.exit_constraints")
            active_contracts = _scalar(exit_constraints.get("active_contracts"), f"{path}.exit_constraints.active_contracts")
            committed_revenue = _money(exit_constraints.get("committed_revenue"), f"{path}.exit_constraints.committed_revenue", currency)
            transition_cost = _money(exit_constraints.get("transition_cost"), f"{path}.exit_constraints.transition_cost", currency)
            earliest_exit = _iso_date(exit_constraints.get("earliest_exit_date"), f"{path}.exit_constraints.earliest_exit_date")
            if any(value is None for value in (active_contracts, committed_revenue, transition_cost)):
                exit_gate = "unknown"
                decision_unknowns.append(f"{path}.exit_constraints")
            elif active_contracts > 0 or committed_revenue > 0 or (as_of is not None and earliest_exit > as_of):
                exit_gate = "blocked"
            else:
                exit_gate = "clear"
            signals: list[str] = []
            if contribution is not None and margin is not None and contribution > 0 and margin >= minimum_margin and demand_status == "confirmed" and (capacity_share is None or capacity_share <= 1):
                signals.append("grow_candidate")
            if demand_status != "confirmed":
                signals.append("test_candidate")
            if contribution is not None and (contribution < 0 or (margin is not None and margin < minimum_margin)) and demand_status == "confirmed":
                signals.append("repair_candidate")
            if contribution is not None and contribution < 0 and fit is not None and fit <= 1 and demand_status == "unknown" and exit_gate == "clear":
                signals.append("retire_candidate")
            if not signals:
                signals.append("hold_candidate")
            advanced = {
                "demand_status": demand_status,
                "exit_gate": exit_gate,
                "decision_signals": signals,
                "exit_transition_cost": _number(transition_cost),
            }
        components[name] = {"revenue": revenue, "variable_cost": variable_cost, "delivery_hours": hours}
        results.append({
            "name": name,
            "status": "complete" if complete else "indeterminate",
            "contribution": _number(contribution),
            "contribution_margin_rate": _number(margin),
            "contribution_per_delivery_hour": _number(per_hour),
            "capacity_share": _number(capacity_share),
            "strategic_fit": _number(fit),
            "flags": flags,
            **advanced,
        })

    if available is None:
        missing.append("available_delivery_hours")
    relationship_output: list[dict[str, Any]] = []
    if mode == "advanced":
        seen_relationships: set[tuple[str, str, str]] = set()
        result_by_name = {item["name"]: item for item in results}
        for index, raw_relationship in enumerate(data.get("relationships", [])):
            path = f"relationships[{index}]"
            relationship = _object(raw_relationship, path)
            source = _string(relationship.get("source"), f"{path}.source")
            target = _string(relationship.get("target"), f"{path}.target")
            if source not in seen or target not in seen:
                raise ValueError(f"{path} references unknown offer")
            relationship_type = relationship.get("type")
            if relationship_type not in RELATIONSHIP_TYPES:
                raise ValueError(f"{path}.type must be supported")
            key = (source, target, str(relationship_type))
            if key in seen_relationships:
                raise ValueError("relationships must be unique")
            seen_relationships.add(key)
            evidence = relationship.get("evidence")
            if evidence not in EVIDENCE_STATES:
                raise ValueError(f"{path}.evidence must be supported")
            flags = [] if evidence == "confirmed" else ["relationship_not_verified"]
            if evidence in {"unknown", "estimated"}:
                decision_unknowns.append(path)
            if relationship_type in {"bundle", "cross_sell"} and evidence in {"confirmed", "reported"}:
                signals = result_by_name[source]["decision_signals"]
                if "bundle_candidate" not in signals:
                    signals.append("bundle_candidate")
            relationship_output.append({"source": source, "target": target, "type": relationship_type, "evidence": evidence, "flags": flags})

    scenario_metrics: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_names: set[str] = set()
        for scenario_index, raw_scenario in enumerate(data.get("scenarios", [])):
            scenario_path = f"scenarios[{scenario_index}]"
            scenario = _object(raw_scenario, scenario_path)
            scenario_name = _string(scenario.get("name"), f"{scenario_path}.name")
            if scenario_name in scenario_names:
                raise ValueError("scenario names must be unique")
            scenario_names.add(scenario_name)
            adjustments: dict[str, tuple[Decimal | None, Decimal | None, Decimal | None]] = {}
            for adjustment_index, raw_adjustment in enumerate(scenario.get("offer_adjustments", [])):
                adjustment_path = f"{scenario_path}.offer_adjustments[{adjustment_index}]"
                adjustment = _object(raw_adjustment, adjustment_path)
                offer_name = _string(adjustment.get("name"), f"{adjustment_path}.name")
                if offer_name not in seen:
                    raise ValueError(f"{adjustment_path} references unknown offer")
                if offer_name in adjustments:
                    raise ValueError(f"{scenario_path}.offer_adjustments names must be unique")
                adjustments[offer_name] = tuple(_scalar(adjustment.get(field), f"{adjustment_path}.{field}") for field in ("revenue_factor", "variable_cost_factor", "delivery_hours_factor"))
            scenario_offers: dict[str, dict[str, int | float | None]] = {}
            total_scenario_hours = Decimal(0)
            for offer_name in sorted(seen):
                part = components[offer_name]
                factors = adjustments.get(offer_name, (Decimal(1), Decimal(1), Decimal(1)))
                revenue_value, cost_value, hours_value = part["revenue"], part["variable_cost"], part["delivery_hours"]
                if any(value is None for value in (revenue_value, cost_value, hours_value, *factors)):
                    scenario_offers[offer_name] = {"contribution": None, "contribution_per_delivery_hour": None, "delivery_hours": None}
                    continue
                scenario_revenue = revenue_value * factors[0]
                scenario_cost = cost_value * factors[1]
                scenario_hours = hours_value * factors[2]
                scenario_contribution = scenario_revenue - scenario_cost
                total_scenario_hours += scenario_hours
                scenario_offers[offer_name] = {
                    "contribution": _number(scenario_contribution),
                    "contribution_per_delivery_hour": _number(scenario_contribution / scenario_hours) if scenario_hours > 0 else None,
                    "delivery_hours": _number(scenario_hours),
                }
            capacity_gap = max(Decimal(0), total_scenario_hours - available) if available is not None else None
            scenario_metrics.append({"name": scenario_name, "offers": scenario_offers, "total_delivery_hours": _number(total_scenario_hours), "capacity_gap_hours": _number(capacity_gap)})

    comparable = [item for item in results if item["contribution_per_delivery_hour"] is not None]
    comparable.sort(key=lambda item: (-item["contribution_per_delivery_hour"], item["name"]))
    missing.extend(decision_unknowns)
    if not comparable:
        quality_status = "indeterminate"
    elif missing:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in results for flag in item["flags"]} | {flag for item in relationship_output for flag in item["flags"]})
    return {
        "currency": currency,
        "period": period,
        "offers": results,
        "portfolio": {
            "status": "complete" if portfolio_complete else "indeterminate",
            "total_revenue": _number(total_revenue) if portfolio_complete else None,
            "total_contribution": _number(total_contribution) if portfolio_complete else None,
            "total_delivery_hours": _number(total_hours) if portfolio_complete else None,
            "unused_delivery_hours": _number(available - total_hours) if portfolio_complete and available is not None else None,
        },
        "economic_order": [item["name"] for item in comparable],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "economic metrics only; strategic fit, demand, and execution risk remain separate",
        "scenario_metrics": scenario_metrics,
        "relationships": relationship_output,
        "analysis_quality": {
            "mode": mode,
            "status": quality_status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": sorted(set(decision_unknowns)),
            "warnings": warnings,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_offer_portfolio.py <input.json>", file=sys.stderr)
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
