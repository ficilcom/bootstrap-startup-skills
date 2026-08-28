#!/usr/bin/env python3
"""Compare growth experiments without conflating economics and launch gates."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
EXPERIMENT_STATUSES = {"proposed", "running", "completed"}
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


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
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
    horizon = _integer(data.get("horizon_weeks"), "horizon_weeks")
    hourly_cost = _money(data.get("internal_hourly_cost"), "internal_hourly_cost", currency)
    weekly_capacity = _scalar(data.get("weekly_execution_capacity_hours"), "weekly_execution_capacity_hours")

    missing: list[str] = []
    decision_unknowns: list[str] = []
    results: list[dict[str, Any]] = []
    components: dict[str, dict[str, Decimal | None]] = {}
    seen: set[str] = set()
    for index, raw_experiment in enumerate(_list(data.get("experiments"), "experiments", nonempty=True)):
        path = f"experiments[{index}]"
        experiment = _object(raw_experiment, path)
        experiment_id = _string(experiment.get("id"), f"{path}.id")
        if experiment_id in seen:
            raise ValueError("experiment ids must be unique")
        seen.add(experiment_id)
        experiment_status = experiment.get("status")
        if experiment_status not in EXPERIMENT_STATUSES:
            raise ValueError(f"{path}.status must be proposed, running, or completed")

        cash_cost = _money(experiment.get("cash_cost"), f"{path}.cash_cost", currency)
        effort = _scalar(experiment.get("effort_hours"), f"{path}.effort_hours")
        contribution = _money(experiment.get("potential_gross_contribution"), f"{path}.potential_gross_contribution", currency)
        probability = _scalar(experiment.get("success_probability"), f"{path}.success_probability")
        if probability is not None and probability > 1:
            raise ValueError(f"{path}.success_probability must be between 0 and 1")
        for field, value in (("cash_cost", cash_cost), ("effort_hours", effort), ("potential_gross_contribution", contribution), ("success_probability", probability)):
            if value is None:
                missing_path = f"{path}.{field}"
                missing.append(missing_path)
                decision_unknowns.append(missing_path)
        if hourly_cost is None:
            missing.append("internal_hourly_cost")
            decision_unknowns.append("internal_hourly_cost")
        if weekly_capacity is None:
            missing.append("weekly_execution_capacity_hours")
            decision_unknowns.append("weekly_execution_capacity_hours")

        internal_cost = total_cost = expected_gross = expected_net = capacity_gap = None
        complete = all(value is not None for value in (cash_cost, effort, contribution, probability, hourly_cost))
        if effort is not None and weekly_capacity is not None:
            capacity_gap = max(Decimal(0), effort - weekly_capacity * horizon)
        if complete:
            assert cash_cost is not None and effort is not None and contribution is not None and probability is not None and hourly_cost is not None
            internal_cost = effort * hourly_cost
            total_cost = cash_cost + internal_cost
            expected_gross = contribution * probability
            expected_net = expected_gross - total_cost

        flags: list[str] = []
        if capacity_gap is not None and capacity_gap > 0:
            flags.append("capacity_exceeded")
        decision = "review"
        sample_sufficient: bool | None = None
        if mode == "advanced":
            advanced_values: dict[str, Decimal | None] = {}
            for field in ("required_sample_size", "available_sample_size", "observed_metric", "success_threshold", "stop_threshold"):
                raw = experiment.get(field)
                value = None if raw is None else _scalar(raw, f"{path}.{field}")
                advanced_values[field] = value
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            raw_stop_loss = experiment.get("stop_loss")
            stop_loss = None if raw_stop_loss is None else _money(raw_stop_loss, f"{path}.stop_loss", currency)
            if stop_loss is None:
                decision_unknowns.append(f"{path}.stop_loss")
            required = advanced_values["required_sample_size"]
            available = advanced_values["available_sample_size"]
            observed = advanced_values["observed_metric"]
            success = advanced_values["success_threshold"]
            stop = advanced_values["stop_threshold"]
            if success is not None and stop is not None and stop >= success:
                raise ValueError(f"{path}.stop_threshold must be less than success_threshold")
            if required is not None and available is not None:
                sample_sufficient = available >= required
                if not sample_sufficient:
                    flags.append("insufficient_sample")
            stop_loss_reached = total_cost is not None and stop_loss is not None and total_cost >= stop_loss
            if stop_loss_reached:
                flags.append("stop_loss_reached")
            advanced_complete = all(value is not None for value in (*advanced_values.values(), stop_loss))
            if not advanced_complete or capacity_gap is None or capacity_gap > 0 or sample_sufficient is not True:
                decision = "hold"
            elif stop_loss_reached:
                decision = "stop"
            elif experiment_status == "completed":
                assert observed is not None and success is not None and stop is not None
                decision = "scale" if observed >= success else "stop" if observed <= stop else "inconclusive"
            else:
                decision = "run"

        components[experiment_id] = {"cash": cash_cost, "effort": effort, "contribution": contribution, "probability": probability, "hourly": hourly_cost}
        results.append({
            "id": experiment_id,
            "experiment_status": experiment_status,
            "status": "complete" if complete else "indeterminate",
            "internal_cost": _number(internal_cost),
            "total_cost": _number(total_cost),
            "expected_gross_contribution": _number(expected_gross),
            "expected_net_value": _number(expected_net),
            "capacity_gap_hours": _number(capacity_gap),
            "sample_sufficient": sample_sufficient,
            "decision_signal": decision,
            "flags": flags,
        })

    comparable = [item for item in results if item["expected_net_value"] is not None]
    comparable.sort(key=lambda item: (-item["expected_net_value"], item["id"]))

    scenario_metrics: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_ids: set[str] = set()
        for index, raw_scenario in enumerate(_list(data.get("scenarios", []), "scenarios")):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            scenario_id = _string(scenario.get("id"), f"{path}.id")
            if scenario_id in scenario_ids:
                raise ValueError("scenario ids must be unique")
            scenario_ids.add(scenario_id)
            factors: dict[str, Decimal | None] = {}
            for field in ("probability_factor", "contribution_factor", "cash_cost_factor"):
                value = _scalar(scenario.get(field), f"{path}.{field}")
                factors[field] = value
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            values: dict[str, int | float | None] = {}
            for experiment_id in sorted(seen):
                part = components[experiment_id]
                required_values = [part[key] for key in ("cash", "effort", "contribution", "probability", "hourly")]
                if any(value is None for value in required_values) or any(value is None for value in factors.values()):
                    values[experiment_id] = None
                    continue
                probability = min(Decimal(1), part["probability"] * factors["probability_factor"])
                expected = part["contribution"] * factors["contribution_factor"] * probability
                cost = part["cash"] * factors["cash_cost_factor"] + part["effort"] * part["hourly"]
                values[experiment_id] = _number(expected - cost)
            scenario_metrics.append({"id": scenario_id, "experiments": values})

    unknowns = sorted(set(decision_unknowns))
    if not comparable:
        quality_status = "indeterminate"
    elif unknowns:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in results for flag in item["flags"]})
    return {
        "currency": currency,
        "horizon_weeks": horizon,
        "experiments": results,
        "economic_order": [item["id"] for item in comparable],
        "ranking_scope": "expected quantified economics only; sample, capacity, evidence, brand, legal, and customer-risk gates remain separate",
        "scenario_metrics": scenario_metrics,
        "missing_inputs": sorted(set(missing)),
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
        print("usage: analyze_growth_experiments.py <input.json>", file=sys.stderr)
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
