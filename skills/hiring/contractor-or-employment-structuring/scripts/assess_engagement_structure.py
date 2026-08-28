#!/usr/bin/env python3
"""Organize contractor engagement observations and size user-supplied reclassification cost."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
OBSERVATIONS = ("independent", "mixed", "employment_like", "unknown")
FEASIBILITY = {"high", "medium", "low"}
FACTORS = (
    "direction_and_control",
    "work_discretion",
    "time_and_place_constraint",
    "remuneration_character",
    "exclusivity",
    "substitutability",
    "equipment_burden",
)
SCENARIOS = ("base", "downside")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


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


def _non_negative_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
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


def _money(value: object, path: str, currency: str) -> Decimal | None:
    return _evidenced(value, path, "amount", currency)


def _scalar(value: object, path: str) -> Decimal | None:
    return _evidenced(value, path, "value")


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

    unknowns: list[str] = []
    warnings: list[str] = []

    engagement = _object(data.get("engagement"), "engagement")
    monthly_fee = _money(engagement.get("monthly_fee"), "engagement.monthly_fee", currency)
    if monthly_fee is None:
        unknowns.append("engagement.monthly_fee")
    months_engaged = _non_negative_integer(engagement.get("months_engaged"), "engagement.months_engaged")
    months_remaining = _non_negative_integer(engagement.get("expected_months_remaining"), "engagement.expected_months_remaining")
    fee_to_date = None if monthly_fee is None else monthly_fee * months_engaged
    remaining_fee = None if monthly_fee is None else monthly_fee * months_remaining

    observations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_factors: set[str] = set()
    for index, raw_factor in enumerate(_list(data.get("factors"), "factors")):
        path = f"factors[{index}]"
        entry = _object(raw_factor, path)
        factor_id = _string(entry.get("id"), f"{path}.id")
        if factor_id in seen_ids:
            raise ValueError("factor ids must be unique")
        seen_ids.add(factor_id)
        name = entry.get("factor")
        if name not in FACTORS:
            raise ValueError(f"{path}.factor must be one of the supported engagement factors")
        if name in seen_factors:
            raise ValueError("factor values must be unique")
        seen_factors.add(name)
        observation = entry.get("observation")
        if observation not in OBSERVATIONS:
            raise ValueError(f"{path}.observation must be independent, mixed, employment_like, or unknown")
        evidence = entry.get("evidence")
        if evidence not in EVIDENCE_STATES:
            raise ValueError(f"{path}.evidence must be supported")
        if (observation == "unknown") != (evidence == "unknown"):
            raise ValueError(f"{path}.evidence must be unknown exactly when the observation is unknown")
        if observation == "unknown":
            unknowns.append(f"{path}.observation")
        note = entry.get("note")
        if note is not None:
            note = _string(note, f"{path}.note")
        observations.append({"id": factor_id, "factor": name, "observation": observation, "evidence": evidence, "note": note})
    if not observations:
        raise ValueError("factors must contain at least one observation")

    counts = {state: sum(1 for entry in observations if entry["observation"] == state) for state in OBSERVATIONS}
    employment_like = sorted(
        (entry for entry in observations if entry["observation"] == "employment_like"),
        key=lambda entry: entry["id"],
    )
    employment_like_ids = [entry["id"] for entry in employment_like]

    reclassification: dict[str, Any] = {}
    mitigations: list[dict[str, Any]] = []
    uncovered = employment_like_ids
    if mode == "advanced":
        assumptions = _object(data.get("reclassification_cost_assumptions", {}), "reclassification_cost_assumptions")
        costs: dict[str, Decimal | None] = {}
        for scenario in SCENARIOS:
            raw = assumptions.get(scenario)
            if raw is None:
                costs[scenario] = None
                unknowns.append(f"reclassification_cost_assumptions.{scenario}")
                continue
            path = f"reclassification_cost_assumptions.{scenario}"
            block = _object(raw, path)
            burden_rate = _scalar(block.get("employer_burden_rate"), f"{path}.employer_burden_rate")
            if burden_rate is None:
                unknowns.append(f"{path}.employer_burden_rate")
            retroactive_months = _non_negative_integer(block.get("retroactive_months"), f"{path}.retroactive_months")
            overtime = _money(block.get("estimated_unpaid_overtime"), f"{path}.estimated_unpaid_overtime", currency)
            if overtime is None:
                unknowns.append(f"{path}.estimated_unpaid_overtime")
            other_total: Decimal | None = Decimal(0)
            for other_index, raw_other in enumerate(_list(block.get("other_costs", []), f"{path}.other_costs")):
                other_path = f"{path}.other_costs[{other_index}]"
                other = _object(raw_other, other_path)
                _string(other.get("name"), f"{other_path}.name")
                amount = _money(other.get("amount"), f"{other_path}.amount", currency)
                if amount is None:
                    unknowns.append(f"{other_path}.amount")
                    other_total = None
                elif other_total is not None:
                    other_total += amount
            parts = [
                None if monthly_fee is None or burden_rate is None else monthly_fee * retroactive_months * burden_rate,
                overtime,
                other_total,
            ]
            costs[scenario] = None if any(part is None for part in parts) else sum(parts, Decimal(0))
        reclassification = {
            "base": _number(costs["base"]),
            "downside": _number(costs["downside"]),
            "base_to_remaining_fee_ratio": _number(
                None if costs["base"] is None or remaining_fee in (None, Decimal(0)) else costs["base"] / remaining_fee
            ),
            "downside_to_remaining_fee_ratio": _number(
                None if costs["downside"] is None or remaining_fee in (None, Decimal(0)) else costs["downside"] / remaining_fee
            ),
        }

        covered_all: set[str] = set()
        seen_mitigations: set[str] = set()
        for index, raw_mitigation in enumerate(_list(data.get("mitigations", []), "mitigations")):
            path = f"mitigations[{index}]"
            mitigation = _object(raw_mitigation, path)
            mitigation_id = _string(mitigation.get("id"), f"{path}.id")
            if mitigation_id in seen_mitigations:
                raise ValueError("mitigation ids must be unique")
            seen_mitigations.add(mitigation_id)
            factor_ids = _list(mitigation.get("factor_ids"), f"{path}.factor_ids")
            if not factor_ids:
                raise ValueError(f"{path}.factor_ids must name at least one factor")
            for factor_id in factor_ids:
                if not isinstance(factor_id, str) or factor_id not in seen_ids:
                    raise ValueError(f"{path}.factor_ids must reference a known factor")
            if len(factor_ids) != len(set(factor_ids)):
                raise ValueError(f"{path}.factor_ids cannot contain duplicates")
            _string(mitigation.get("change"), f"{path}.change")
            feasibility = mitigation.get("feasibility")
            if feasibility not in FEASIBILITY:
                raise ValueError(f"{path}.feasibility must be high, medium, or low")
            cost = _money(mitigation.get("cost"), f"{path}.cost", currency)
            if cost is None:
                unknowns.append(f"{path}.cost")
            _string(mitigation.get("business_impact"), f"{path}.business_impact")
            covered = sorted(set(factor_ids) & set(employment_like_ids))
            covered_all.update(covered)
            mitigations.append(
                {
                    "id": mitigation_id,
                    "factor_ids": list(factor_ids),
                    "covered_employment_like_factors": covered,
                    "addresses_no_employment_like_factor": not covered,
                    "feasibility": feasibility,
                    "cost": _number(cost),
                }
            )
        uncovered = sorted(set(employment_like_ids) - covered_all)

    if all(entry["observation"] == "unknown" for entry in observations):
        status = "indeterminate"
    elif unknowns or warnings:
        status = "partial"
    else:
        status = "complete"

    return {
        "currency": currency,
        "engagement_economics": {
            "monthly_fee": _number(monthly_fee),
            "months_engaged": months_engaged,
            "expected_months_remaining": months_remaining,
            "fee_to_date": _number(fee_to_date),
            "remaining_fee": _number(remaining_fee),
        },
        "observation_counts": counts,
        "factors": observations,
        "factors_not_supplied": sorted(set(FACTORS) - seen_factors),
        "employment_like_factors": [
            {"id": entry["id"], "factor": entry["factor"], "evidence": entry["evidence"]} for entry in employment_like
        ],
        "employment_like_factors_uncovered": uncovered,
        "unknown_factors": sorted(entry["id"] for entry in observations if entry["observation"] == "unknown"),
        "risk_signal_count": counts["employment_like"],
        "mixed_signal_count": counts["mixed"],
        "reclassification_cost": reclassification,
        "mitigations": mitigations,
        "classification_scope": "observation tally and user-supplied cost arithmetic only; classification, administrative or judicial determination, insurance and tax liability, and remedy remain separate",
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
        print("usage: assess_engagement_structure.py <input.json>", file=sys.stderr)
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
