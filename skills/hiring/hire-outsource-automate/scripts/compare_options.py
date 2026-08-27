#!/usr/bin/env python3
"""Compare work-coverage options from an evidence-tagged JSON model."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from decimal import Decimal
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
KINDS = {"hire", "outsource", "automate", "defer_or_stop"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
LEVELS = {"low", "medium", "high"}
VARIABILITY = {"steady", "cyclical", "volatile"}
QUALITY_CONTROL = {"direct", "shared", "limited"}
BENEFIT_CATEGORIES = {"incremental_revenue", "cost_avoidance", "loss_avoidance"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

COST_FIELDS = {
    "hire": {
        "one_time": {"recruiting", "onboarding", "equipment", "exit_or_switching"},
        "recurring_per_period": {
            "compensation",
            "employer_burdens_and_benefits",
            "management",
            "tools_and_workspace",
        },
    },
    "outsource": {
        "one_time": {"sourcing_and_contracting", "transition", "switching_or_exit"},
        "recurring_per_period": {"contract", "vendor_management", "internal_quality_review"},
    },
    "automate": {
        "one_time": {"build", "integration_and_data_migration", "rollback_or_replacement"},
        "recurring_per_period": {
            "software_and_infrastructure",
            "maintenance",
            "monitoring",
            "failure_handling",
        },
    },
    "defer_or_stop": {
        "one_time": {"wind_down", "restart_or_replacement"},
        "recurring_per_period": {"residual_obligations", "management"},
    },
}


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a nonnegative number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{path} must be finite")
    if result < 0:
        raise ValueError(f"{path} must be nonnegative")
    return result


def _evidence_value(
    value: object,
    path: str,
    *,
    value_key: str,
    currency: str | None = None,
    minimum: Decimal = Decimal(0),
    maximum: Decimal | None = None,
    integer: bool = False,
) -> tuple[Decimal | None, str]:
    entry = _require_object(value, path)
    evidence = entry.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    if currency is not None and entry.get("currency", currency) != currency:
        raise ValueError(f"{path}.currency must match top-level currency")
    raw = entry.get(value_key)
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown {value_key} must be null")
        return None, evidence
    if raw is None:
        raise ValueError(f"{path}.{value_key} is required when evidence is known")
    result = _decimal(raw, f"{path}.{value_key}")
    if result < minimum:
        raise ValueError(f"{path}.{value_key} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{path}.{value_key} must be at most {maximum}")
    if integer and result != result.to_integral_value():
        raise ValueError(f"{path}.{value_key} must be a whole number")
    return result, evidence


def _money(value: object, path: str, currency: str) -> tuple[Decimal | None, str]:
    return _evidence_value(value, path, value_key="amount", currency=currency)


def _scalar(
    value: object,
    path: str,
    *,
    minimum: Decimal = Decimal(0),
    maximum: Decimal | None = None,
    integer: bool = False,
) -> tuple[Decimal | None, str]:
    return _evidence_value(
        value,
        path,
        value_key="value",
        minimum=minimum,
        maximum=maximum,
        integer=integer,
    )


def _validate_costs(candidate: dict[str, Any], path: str, currency: str) -> None:
    costs = _require_object(candidate.get("costs"), f"{path}.costs")
    expected = COST_FIELDS[candidate["kind"]]
    if set(costs) != set(expected):
        raise ValueError(f"{path}.costs must contain one_time and recurring_per_period")
    for bucket, fields in expected.items():
        entries = _require_object(costs.get(bucket), f"{path}.costs.{bucket}")
        if set(entries) != fields:
            raise ValueError(f"{path}.costs.{bucket} must contain exactly the required cost fields")
        for field, value in entries.items():
            _money(value, f"{path}.costs.{bucket}.{field}", currency)


def _validate_fit(candidate: dict[str, Any], path: str) -> None:
    fit = _require_object(candidate.get("fit"), f"{path}.fit")
    expected = {
        "workload_hours_per_period",
        "workload_variability",
        "strategic_importance",
        "confidentiality",
        "quality_control",
        "time_to_readiness_periods",
        "reversibility",
        "internal_learning_value",
        "management_overhead_hours_per_period",
    }
    if set(fit) != expected:
        raise ValueError(f"{path}.fit must contain exactly the comparison criteria")
    _scalar(fit["workload_hours_per_period"], f"{path}.fit.workload_hours_per_period")
    if fit["workload_variability"] not in VARIABILITY:
        raise ValueError(f"{path}.fit.workload_variability must be steady, cyclical, or volatile")
    for field in ("strategic_importance", "confidentiality", "reversibility", "internal_learning_value"):
        if fit[field] not in LEVELS:
            raise ValueError(f"{path}.fit.{field} must be low, medium, or high")
    if fit["quality_control"] not in QUALITY_CONTROL:
        raise ValueError(f"{path}.fit.quality_control must be direct, shared, or limited")
    _scalar(
        fit["time_to_readiness_periods"],
        f"{path}.fit.time_to_readiness_periods",
        integer=True,
    )
    _scalar(
        fit["management_overhead_hours_per_period"],
        f"{path}.fit.management_overhead_hours_per_period",
    )


def _validate_candidate(candidate: object, index: int, currency: str) -> str:
    path = f"candidate {index}"
    entry = _require_object(candidate, path)
    name = _require_string(entry.get("name"), f"{path}.name")
    if entry.get("kind") not in KINDS:
        raise ValueError(f"{path}.kind must be hire, outsource, automate, or defer_or_stop")
    _validate_fit(entry, path)
    _validate_costs(entry, path, currency)
    benefits = entry.get("benefits_per_ready_period")
    if not isinstance(benefits, list):
        raise ValueError(f"{path}.benefits_per_ready_period must be a list")
    for benefit_index, benefit in enumerate(benefits):
        benefit_path = f"{path}.benefits_per_ready_period {benefit_index}"
        item = _require_object(benefit, benefit_path)
        if set(item) != {"category", "label", "amount"}:
            raise ValueError(f"{benefit_path} must contain category, label, and amount")
        if item["category"] not in BENEFIT_CATEGORIES:
            raise ValueError(f"{benefit_path}.category must be a supported benefit category")
        _require_string(item["label"], f"{benefit_path}.label")
        _money(item["amount"], f"{benefit_path}.amount", currency)
    pessimistic = entry.get("pessimistic_case")
    if pessimistic is not None:
        case = _require_object(pessimistic, f"{path}.pessimistic_case")
        if set(case) != {"benefit_multiplier", "cost_multiplier"}:
            raise ValueError(f"{path}.pessimistic_case must contain both multipliers")
        _scalar(
            case["benefit_multiplier"],
            f"{path}.pessimistic_case.benefit_multiplier",
            maximum=Decimal(1),
        )
        _scalar(
            case["cost_multiplier"],
            f"{path}.pessimistic_case.cost_multiplier",
            minimum=Decimal(1),
        )
    return name


def validate(payload: object) -> None:
    data = _require_object(payload, "input")
    if set(data) != {"currency", "period_unit", "horizon_periods", "candidates"}:
        raise ValueError("input must contain currency, period_unit, horizon_periods, and candidates")
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    if data.get("period_unit") not in PERIOD_UNITS:
        raise ValueError("period_unit must be week, month, quarter, or year")
    horizon = data.get("horizon_periods")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("horizon_periods must be a positive whole number")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")
    names: set[str] = set()
    for index, candidate in enumerate(candidates):
        name = _validate_candidate(candidate, index, currency)
        if name in names:
            raise ValueError(f"duplicate candidate name {name}")
        names.add(name)


def _int_or_decimal(value: Decimal) -> int | Decimal:
    return int(value) if value == value.to_integral_value() else value


def _case_result(
    *,
    one_time_cost: Decimal,
    recurring_cost: Decimal,
    benefit: Decimal,
    readiness: int,
    horizon: int,
) -> dict[str, Any]:
    active_periods = max(0, horizon - readiness)
    total_cost = one_time_cost + recurring_cost * horizon
    total_benefit = benefit * active_periods
    net = total_benefit - total_cost
    cumulative = -one_time_cost
    payback: int | str = "not_within_horizon"
    for period in range(1, horizon + 1):
        cumulative -= recurring_cost
        if period > readiness:
            cumulative += benefit
        if cumulative >= 0:
            payback = period
            break
    if isinstance(payback, str) and benefit <= recurring_cost:
        payback = "not_recoverable_within_horizon"
    status = "positive_net_within_horizon" if net >= 0 else "negative_net_within_horizon"
    return {
        "one_time_cost": _int_or_decimal(one_time_cost),
        "recurring_cost_per_period": _int_or_decimal(recurring_cost),
        "benefit_per_ready_period": _int_or_decimal(benefit),
        "benefit_active_periods": active_periods,
        "total_cost": _int_or_decimal(total_cost),
        "total_quantified_benefit": _int_or_decimal(total_benefit),
        "net_quantified_effect": _int_or_decimal(net),
        "payback_periods": payback,
        "economic_status": status,
    }


def _candidate_result(candidate: dict[str, Any], currency: str, horizon: int) -> dict[str, Any]:
    name = candidate["name"]
    path = f"candidate {name}"
    missing: list[str] = []
    core_missing: list[str] = []
    estimate_based = False

    def collect(
        value: Decimal | None,
        evidence: str,
        field: str,
        *,
        required_for_economics: bool = False,
    ) -> Decimal | None:
        nonlocal estimate_based
        if evidence == "unknown":
            missing.append(field)
            if required_for_economics:
                core_missing.append(field)
        elif evidence == "estimated":
            estimate_based = True
        return value

    fit = candidate["fit"]
    readiness_raw, readiness_evidence = _scalar(
        fit["time_to_readiness_periods"], f"{path}.fit.time_to_readiness_periods", integer=True
    )
    readiness = collect(
        readiness_raw,
        readiness_evidence,
        "fit.time_to_readiness_periods",
        required_for_economics=True,
    )
    workload_raw, workload_evidence = _scalar(
        fit["workload_hours_per_period"], f"{path}.fit.workload_hours_per_period"
    )
    workload = collect(workload_raw, workload_evidence, "fit.workload_hours_per_period")
    management_overhead_raw, management_overhead_evidence = _scalar(
        fit["management_overhead_hours_per_period"],
        f"{path}.fit.management_overhead_hours_per_period",
    )
    management_overhead = collect(
        management_overhead_raw,
        management_overhead_evidence,
        "fit.management_overhead_hours_per_period",
    )

    totals: dict[str, Decimal] = {"one_time": Decimal(0), "recurring_per_period": Decimal(0)}
    for bucket, entries in candidate["costs"].items():
        for field, raw in entries.items():
            value, evidence = _money(raw, f"{path}.costs.{bucket}.{field}", currency)
            parsed = collect(
                value,
                evidence,
                f"costs.{bucket}.{field}",
                required_for_economics=True,
            )
            if parsed is not None:
                totals[bucket] += parsed

    benefit_by_category: dict[str, Decimal] = {category: Decimal(0) for category in BENEFIT_CATEGORIES}
    benefits_output: list[dict[str, Any]] = []
    for index, item in enumerate(candidate["benefits_per_ready_period"]):
        value, evidence = _money(item["amount"], f"{path}.benefits_per_ready_period {index}.amount", currency)
        parsed = collect(
            value,
            evidence,
            f"benefits_per_ready_period.{index}.amount",
            required_for_economics=True,
        )
        if parsed is not None:
            benefit_by_category[item["category"]] += parsed
        benefits_output.append(
            {"category": item["category"], "label": item["label"], "evidence": evidence, "amount": _int_or_decimal(parsed) if parsed is not None else None}
        )

    qualitative = {
        "workload_hours_per_period": {
            "value": _int_or_decimal(workload) if workload is not None else None,
            "evidence": workload_evidence,
        },
        "workload_variability": fit["workload_variability"],
        "strategic_importance": fit["strategic_importance"],
        "confidentiality": fit["confidentiality"],
        "quality_control": fit["quality_control"],
        "time_to_readiness_periods": {
            "value": _int_or_decimal(readiness) if readiness is not None else None,
            "evidence": readiness_evidence,
        },
        "reversibility": fit["reversibility"],
        "internal_learning_value": fit["internal_learning_value"],
        "management_overhead_hours_per_period": {
            "value": _int_or_decimal(management_overhead) if management_overhead is not None else None,
            "evidence": management_overhead_evidence,
        },
    }
    result: dict[str, Any] = {
        "name": name,
        "kind": candidate["kind"],
        "fit": qualitative,
        "benefit_components_per_ready_period": benefits_output,
        "benefit_by_category_per_ready_period": {key: _int_or_decimal(value) for key, value in benefit_by_category.items()},
        "missing_inputs": missing,
        "estimate_based": estimate_based,
    }
    if core_missing:
        result["base_case"] = "indeterminate"
        result["pessimistic_case"] = "not_calculated_due_to_unknown_base_inputs"
        return result

    assert readiness is not None
    base = _case_result(
        one_time_cost=totals["one_time"],
        recurring_cost=totals["recurring_per_period"],
        benefit=sum(benefit_by_category.values(), Decimal(0)),
        readiness=int(readiness),
        horizon=horizon,
    )
    result["base_case"] = base
    case = candidate.get("pessimistic_case")
    if case is None:
        result["pessimistic_case"] = "not_provided"
        return result
    benefit_multiplier, benefit_evidence = _scalar(
        case["benefit_multiplier"], f"{path}.pessimistic_case.benefit_multiplier", maximum=Decimal(1)
    )
    cost_multiplier, cost_evidence = _scalar(
        case["cost_multiplier"], f"{path}.pessimistic_case.cost_multiplier", minimum=Decimal(1)
    )
    if benefit_evidence == "estimated" or cost_evidence == "estimated":
        result["estimate_based"] = True
    if benefit_multiplier is None or cost_multiplier is None:
        result["pessimistic_case"] = "indeterminate"
        result["missing_inputs"].extend(
            field
            for field, value in (
                ("pessimistic_case.benefit_multiplier", benefit_multiplier),
                ("pessimistic_case.cost_multiplier", cost_multiplier),
            )
            if value is None
        )
        return result
    result["pessimistic_case"] = _case_result(
        one_time_cost=totals["one_time"] * cost_multiplier,
        recurring_cost=totals["recurring_per_period"] * cost_multiplier,
        benefit=sum(benefit_by_category.values(), Decimal(0)) * benefit_multiplier,
        readiness=int(readiness),
        horizon=horizon,
    )
    return result


def calculate(payload: object) -> dict[str, Any]:
    validate(payload)
    data = _require_object(payload, "input")
    currency = data["currency"]
    horizon = data["horizon_periods"]
    candidates = [_candidate_result(item, currency, horizon) for item in data["candidates"]]
    rankable = [item for item in candidates if isinstance(item["base_case"], dict)]
    ranking = [
        item["name"]
        for item in sorted(
            rankable,
            key=lambda item: item["base_case"]["net_quantified_effect"],
            reverse=True,
        )
    ]
    return {
        "currency": currency,
        "period_unit": data["period_unit"],
        "horizon_periods": horizon,
        "candidates": candidates,
        "economic_ranking": ranking,
        "economic_ranking_scope": "quantified net effect only; it excludes qualitative fit and execution gates",
    }


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input file, or - for standard input")
    args = parser.parse_args(argv)
    try:
        with (sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")) as stream:
            payload = json.load(stream)
        print(json.dumps(calculate(payload), ensure_ascii=False, default=_json_default, separators=(",", ":")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
