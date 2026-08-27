#!/usr/bin/env python3
"""Identify dependency single points, recovery gaps, and transitive blast radius."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
DEPENDENCY_TYPES = {"person", "customer", "vendor", "system", "process", "facility", "data", "other"}


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
        })

    ranked = [item for item in results if item["risk_score"] is not None]
    ranked.sort(key=lambda item: (-item["risk_score"], item["name"]))
    return {
        "review_date": review_date,
        "dependencies": results,
        "risk_order": [item["name"] for item in ranked],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "modeled likelihood, criticality, recovery, and blast radius; not an incident forecast",
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
