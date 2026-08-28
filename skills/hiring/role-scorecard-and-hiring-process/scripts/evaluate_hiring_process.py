#!/usr/bin/env python3
"""Evaluate anonymized candidates against evidence and hiring gates."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
CRITERION_KINDS = {"outcome", "competency", "must"}
PROCESS_STATUSES = {"verified", "reported", "unknown", "failed"}


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


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


def _rating_limit(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        raise ValueError(f"{path} must be an integer between 0 and 5")
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


def _evidenced_rating(value: object, path: str) -> Decimal | None:
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
    result = _decimal(raw, f"{path}.value")
    if result > 5:
        raise ValueError(f"{path}.value must be between 0 and 5")
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


def _weighted_score(ratings: dict[str, Decimal | None], weights: dict[str, int]) -> Decimal | None:
    if set(ratings) != set(weights) or any(value is None for value in ratings.values()):
        return None
    total_weight = sum(weights.values())
    return sum(ratings[key] * weights[key] for key in weights) / total_weight


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    role_id = _string(data.get("role_id"), "role_id")

    criteria: dict[str, dict[str, Any]] = {}
    weights: dict[str, int] = {}
    for index, raw_criterion in enumerate(_list(data.get("criteria"), "criteria", nonempty=True)):
        path = f"criteria[{index}]"
        criterion = _object(raw_criterion, path)
        criterion_id = _string(criterion.get("id"), f"{path}.id")
        if criterion_id in criteria:
            raise ValueError("criterion ids must be unique")
        kind = criterion.get("kind")
        if kind not in CRITERION_KINDS:
            raise ValueError(f"{path}.kind must be outcome, competency, or must")
        weight = _positive_integer(criterion.get("weight"), f"{path}.weight")
        minimum = _rating_limit(criterion.get("minimum_rating"), f"{path}.minimum_rating")
        criteria[criterion_id] = {"kind": kind, "minimum": Decimal(minimum)}
        weights[criterion_id] = weight

    process_checks: dict[str, bool] = {}
    if mode == "advanced":
        for index, raw_check in enumerate(_list(data.get("process_checks", []), "process_checks")):
            path = f"process_checks[{index}]"
            check = _object(raw_check, path)
            check_id = _string(check.get("id"), f"{path}.id")
            if check_id in process_checks:
                raise ValueError("process check ids must be unique")
            required = check.get("required")
            if not isinstance(required, bool):
                raise ValueError(f"{path}.required must be boolean")
            process_checks[check_id] = required

    decision_unknowns: list[str] = []
    candidate_ratings: dict[str, dict[str, Decimal | None]] = {}
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_candidate in enumerate(_list(data.get("candidates"), "candidates", nonempty=True)):
        path = f"candidates[{index}]"
        candidate = _object(raw_candidate, path)
        candidate_id = _string(candidate.get("id"), f"{path}.id")
        if candidate_id in seen:
            raise ValueError("candidate ids must be unique")
        seen.add(candidate_id)
        ratings: dict[str, Decimal | None] = {}
        for evaluation_index, raw_evaluation in enumerate(_list(candidate.get("evaluations"), f"{path}.evaluations")):
            evaluation_path = f"{path}.evaluations[{evaluation_index}]"
            evaluation = _object(raw_evaluation, evaluation_path)
            criterion_id = _string(evaluation.get("id"), f"{evaluation_path}.id")
            if criterion_id not in criteria:
                raise ValueError(f"{evaluation_path} references unknown criterion {criterion_id}")
            if criterion_id in ratings:
                raise ValueError(f"{path}.evaluations ids must be unique")
            ratings[criterion_id] = _evidenced_rating(evaluation.get("rating"), f"{evaluation_path}.rating")
        for criterion_id in criteria:
            if criterion_id not in ratings:
                ratings[criterion_id] = None
            if ratings[criterion_id] is None:
                decision_unknowns.append(f"{path}.criteria.{criterion_id}")

        failed_gates = sorted(criterion_id for criterion_id, spec in criteria.items() if spec["kind"] == "must" and ratings[criterion_id] is not None and ratings[criterion_id] < spec["minimum"])
        unknown_gates = sorted(criterion_id for criterion_id, spec in criteria.items() if spec["kind"] == "must" and ratings[criterion_id] is None)
        validation_targets = sorted(criterion_id for criterion_id, value in ratings.items() if value is None)

        if mode == "advanced":
            process_results: dict[str, str] = {}
            for result_index, raw_result in enumerate(_list(candidate.get("process_results", []), f"{path}.process_results")):
                result_path = f"{path}.process_results[{result_index}]"
                result = _object(raw_result, result_path)
                check_id = _string(result.get("id"), f"{result_path}.id")
                if check_id not in process_checks:
                    raise ValueError(f"{result_path} references unknown process check {check_id}")
                if check_id in process_results:
                    raise ValueError(f"{path}.process_results ids must be unique")
                status = result.get("status")
                if status not in PROCESS_STATUSES:
                    raise ValueError(f"{result_path}.status must be supported")
                process_results[check_id] = str(status)
            for check_id, required in process_checks.items():
                status = process_results.get(check_id)
                if status in {"reported", "unknown", None}:
                    validation_targets.append(check_id)
                if required and status == "failed":
                    failed_gates.append(check_id)
                elif required and status != "verified":
                    unknown_gates.append(check_id)
                    decision_unknowns.append(f"{path}.process.{check_id}")

        failed_gates = sorted(set(failed_gates))
        unknown_gates = sorted(set(unknown_gates))
        score = _weighted_score(ratings, weights)
        if failed_gates:
            eligibility = "disqualified"
            signal = "do_not_advance"
        elif unknown_gates:
            eligibility = "conditional"
            signal = "hold"
        else:
            eligibility = "eligible"
            signal = "advance" if score is not None else "hold"
        flags: list[str] = []
        if failed_gates:
            flags.append("failed_gate")
        if unknown_gates:
            flags.append("unknown_gate")
        if score is None:
            flags.append("incomplete_score")
        candidate_ratings[candidate_id] = ratings
        results.append({
            "id": candidate_id,
            "weighted_score": _number(score),
            "eligibility_status": eligibility,
            "failed_gates": failed_gates,
            "unknown_gates": unknown_gates,
            "validation_targets": sorted(set(validation_targets)),
            "decision_signal": signal,
            "flags": flags,
        })

    ranked = [item for item in results if item["weighted_score"] is not None]
    ranked.sort(key=lambda item: (-item["weighted_score"], item["id"]))
    scenario_scores: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_ids: set[str] = set()
        for index, raw_scenario in enumerate(_list(data.get("scenarios", []), "scenarios")):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            scenario_id = _string(scenario.get("id"), f"{path}.id")
            if scenario_id in scenario_ids:
                raise ValueError("scenario ids must be unique")
            scenario_ids.add(scenario_id)
            scenario_weights = dict(weights)
            override_ids: set[str] = set()
            for override_index, raw_override in enumerate(_list(scenario.get("weight_overrides"), f"{path}.weight_overrides", nonempty=True)):
                override_path = f"{path}.weight_overrides[{override_index}]"
                override = _object(raw_override, override_path)
                criterion_id = _string(override.get("id"), f"{override_path}.id")
                if criterion_id not in criteria:
                    raise ValueError(f"{override_path} references unknown criterion {criterion_id}")
                if criterion_id in override_ids:
                    raise ValueError(f"{path}.weight_overrides ids must be unique")
                override_ids.add(criterion_id)
                scenario_weights[criterion_id] = _positive_integer(override.get("weight"), f"{override_path}.weight")
            scenario_scores.append({"id": scenario_id, "candidates": {candidate_id: _number(_weighted_score(candidate_ratings[candidate_id], scenario_weights)) for candidate_id in sorted(seen)}})

    unknowns = sorted(set(decision_unknowns))
    if not ranked:
        quality_status = "indeterminate"
    elif unknowns:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in results for flag in item["flags"]})
    return {
        "role_id": role_id,
        "candidates": results,
        "evidence_order": [item["id"] for item in ranked],
        "ranking_scope": "complete evidenced weighted ratings only; must criteria, process gates, fairness, references, compensation, and authority remain separate",
        "scenario_scores": scenario_scores,
        "analysis_quality": {"mode": mode, "status": quality_status, "evidence_counts": _evidence_counts(data), "decision_changing_unknowns": unknowns, "warnings": warnings},
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: evaluate_hiring_process.py <input.json>", file=sys.stderr)
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
