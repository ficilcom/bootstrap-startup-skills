#!/usr/bin/env python3
"""Identify dependency single points, recovery gaps, and transitive blast radius."""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
DEPENDENCY_TYPES = {"person", "customer", "vendor", "system", "process", "facility", "data", "other"}
ANALYSIS_MODES = {"core", "advanced"}
TEST_RESULTS = {"passed", "failed", "not_run", "unknown"}


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        requirement = "a non-empty list" if nonempty else "a list"
        raise ValueError(f"{path} must be {requirement}")
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
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{path} must be an integer between 1 and 5")
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


def _optional_iso_date(value: object, path: str) -> str | None:
    if value is None:
        return None
    text = _string(value, path)
    try:
        date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error
    return text


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


def _recovery_layers(graph: dict[str, list[str]]) -> list[list[str]]:
    remaining = set(graph)
    completed: set[str] = set()
    layers: list[list[str]] = []
    while remaining:
        layer = sorted(name for name in remaining if set(graph[name]) <= completed)
        if not layer:
            raise ValueError("dependency graph must not contain a cycle")
        layers.append(layer)
        completed.update(layer)
        remaining.difference_update(layer)
    return layers


def _assert_acyclic(graph: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("dependency graph must not contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _affected(name: str, reverse_graph: dict[str, list[str]]) -> list[str]:
    found: set[str] = set()
    pending = list(reverse_graph[name])
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(reverse_graph[current])
    return sorted(found)


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    review_date = _string(data.get("review_date"), "review_date")
    raw_items = _list(data.get("dependencies"), "dependencies", nonempty=True)
    parsed: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        path = f"dependencies[{index}]"
        item = _object(raw_item, path)
        name = _string(item.get("name"), f"{path}.name")
        if name in names:
            raise ValueError("dependency names must be unique")
        names.add(name)
        dependency_type = item.get("type")
        if dependency_type not in DEPENDENCY_TYPES:
            raise ValueError(f"{path}.type must be supported")
        depends_on = [_string(value, f"{path}.depends_on") for value in _list(item.get("depends_on"), f"{path}.depends_on")]
        if len(depends_on) != len(set(depends_on)):
            raise ValueError(f"{path}.depends_on must be unique")
        parsed.append({"path": path, "raw": item, "name": name, "type": dependency_type, "depends_on": depends_on})

    graph = {item["name"]: item["depends_on"] for item in parsed}
    for name, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in names:
                raise ValueError(f"{name} references unknown dependency {dependency}")
    _assert_acyclic(graph)
    reverse_graph = {name: [] for name in names}
    for dependent, dependencies in graph.items():
        for dependency in dependencies:
            reverse_graph[dependency].append(dependent)

    missing: list[str] = []
    decision_unknowns: list[str] = []
    results: list[dict[str, Any]] = []
    for item in parsed:
        path = item["path"]
        raw = item["raw"]
        criticality = _score(raw.get("criticality"), f"{path}.criticality")
        probability = _scalar(raw.get("outage_probability"), f"{path}.outage_probability")
        if probability is not None and probability > 1:
            raise ValueError(f"{path}.outage_probability must be between 0 and 1")
        tolerance = _scalar(raw.get("maximum_tolerable_downtime_hours"), f"{path}.maximum_tolerable_downtime_hours")
        recovery = _scalar(raw.get("expected_recovery_hours"), f"{path}.expected_recovery_hours")
        tested = raw.get("tested_alternative")
        if not isinstance(tested, bool):
            raise ValueError(f"{path}.tested_alternative must be boolean")
        owner_value = raw.get("owner")
        owner = owner_value.strip() if isinstance(owner_value, str) and owner_value.strip() else None
        for field, value in (("outage_probability", probability), ("maximum_tolerable_downtime_hours", tolerance), ("expected_recovery_hours", recovery)):
            if value is None:
                missing.append(f"{path}.{field}")
        complete = probability is not None and tolerance is not None and recovery is not None and tolerance > 0
        affected = _affected(item["name"], reverse_graph)
        gap = risk = None
        flags: list[str] = []
        if complete:
            assert probability is not None and tolerance is not None and recovery is not None
            gap = max(Decimal(0), recovery - tolerance)
            recovery_factor = max(Decimal(1), recovery / tolerance)
            risk = Decimal(criticality) * probability * recovery_factor * Decimal(1 + len(affected))
            if recovery > tolerance:
                flags.append("recovery_exceeds_tolerance")
        if not tested:
            flags.append("no_tested_alternative")
        if owner is None:
            flags.append("missing_owner")
        advanced: dict[str, Any] = {}
        if mode == "advanced":
            advanced_values: dict[str, Decimal | None] = {}
            for field in (
                "recovery_point_objective_hours",
                "expected_data_loss_hours",
                "minimum_operating_capacity_rate",
                "alternative_capacity_rate",
                "alternative_recovery_hours",
            ):
                raw_value = raw.get(field)
                value = _scalar(raw_value, f"{path}.{field}") if raw_value is not None else None
                advanced_values[field] = value
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            for field in ("minimum_operating_capacity_rate", "alternative_capacity_rate"):
                value = advanced_values[field]
                if value is not None and value > 1:
                    raise ValueError(f"{path}.{field} must be between 0 and 1")
            test_result = raw.get("test_result", "unknown")
            if test_result not in TEST_RESULTS:
                raise ValueError(f"{path}.test_result must be supported")
            if test_result in {"passed", "failed"} and not tested:
                raise ValueError(f"{path}.test_result contradicts tested_alternative")
            if test_result == "not_run" and tested:
                raise ValueError(f"{path}.test_result contradicts tested_alternative")
            last_test_date = _optional_iso_date(raw.get("last_test_date"), f"{path}.last_test_date")
            if test_result == "unknown":
                decision_unknowns.append(f"{path}.test_result")
            rpo = advanced_values["recovery_point_objective_hours"]
            data_loss = advanced_values["expected_data_loss_hours"]
            minimum_capacity = advanced_values["minimum_operating_capacity_rate"]
            alternative_capacity = advanced_values["alternative_capacity_rate"]
            alternative_recovery = advanced_values["alternative_recovery_hours"]
            rpo_gap = max(Decimal(0), data_loss - rpo) if rpo is not None and data_loss is not None else None
            capacity_gap = max(Decimal(0), minimum_capacity - alternative_capacity) if minimum_capacity is not None and alternative_capacity is not None else None
            if rpo_gap is not None and rpo_gap > 0:
                flags.append("rpo_exceeded")
            if capacity_gap is not None and capacity_gap > 0:
                flags.append("alternative_capacity_below_minimum")
            if alternative_recovery is not None and tolerance is not None and alternative_recovery > tolerance:
                flags.append("alternative_recovery_exceeds_tolerance")
            if test_result == "failed":
                flags.append("recovery_test_failed")
            has_breach = any(flag in flags for flag in ("recovery_exceeds_tolerance", "rpo_exceeded", "alternative_capacity_below_minimum", "alternative_recovery_exceeds_tolerance", "recovery_test_failed"))
            if any(f"{path}." in item for item in decision_unknowns):
                priority = "review_required"
            elif criticality == 5 and has_breach:
                priority = "critical"
            elif criticality >= 4 and (has_breach or test_result != "passed"):
                priority = "high"
            elif has_breach or test_result != "passed":
                priority = "medium"
            else:
                priority = "monitor"
            advanced = {
                "rpo_gap_hours": _number(rpo_gap),
                "alternative_capacity_gap_rate": _number(capacity_gap),
                "alternative_recovery_hours": _number(alternative_recovery),
                "last_test_date": last_test_date,
                "test_result": test_result,
                "priority_tier": priority,
            }
        results.append({
            "name": item["name"],
            "type": item["type"],
            "status": "complete" if complete else "indeterminate",
            "owner": owner,
            "recovery_gap_hours": _number(gap),
            "affected_dependencies": affected,
            "blast_radius_count": len(affected),
            "risk_score": _number(risk),
            "flags": flags,
            **advanced,
        })

    ranked = [item for item in results if item["risk_score"] is not None]
    ranked.sort(key=lambda item: (-item["risk_score"], item["name"]))
    scenario_impacts: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_names: set[str] = set()
        for index, raw_scenario in enumerate(data.get("scenarios", [])):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            name = _string(scenario.get("name"), f"{path}.name")
            if name in scenario_names:
                raise ValueError("scenario names must be unique")
            scenario_names.add(name)
            failed = sorted({_string(value, f"{path}.failed_dependencies") for value in _list(scenario.get("failed_dependencies"), f"{path}.failed_dependencies", nonempty=True)})
            for dependency in failed:
                if dependency not in names:
                    raise ValueError(f"{path} references unknown dependency {dependency}")
            affected = set(failed)
            for dependency in failed:
                affected.update(_affected(dependency, reverse_graph))
            scenario_impacts.append({"name": name, "failed_dependencies": failed, "affected_dependencies": sorted(affected)})

    missing.extend(decision_unknowns)
    if not ranked:
        quality_status = "indeterminate"
    elif missing:
        quality_status = "partial"
    else:
        quality_status = "complete"
    return {
        "review_date": review_date,
        "dependencies": results,
        "risk_order": [item["name"] for item in ranked],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "modeled likelihood, criticality, recovery, and blast radius; not an incident forecast",
        "recovery_layers": _recovery_layers(graph) if mode == "advanced" else [],
        "scenario_impacts": scenario_impacts,
        "analysis_quality": {
            "mode": mode,
            "status": quality_status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": sorted(set(decision_unknowns)),
            "warnings": sorted({flag for item in results for flag in item["flags"]}),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_continuity.py <input.json>", file=sys.stderr)
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
