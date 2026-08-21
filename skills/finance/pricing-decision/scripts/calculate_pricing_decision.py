#!/usr/bin/env python3
"""Calculate pricing proposal impact from an anonymous JSON model."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date
from decimal import Decimal
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"recurring", "transactional", "service_project"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
PRICING_MODELS = {"flat", "base_plus_usage", "percentage", "quoted"}
MIGRATION_POLICIES = {
    "immediate",
    "renewal",
    "delayed",
    "grandfathered",
    "phased",
    "manual_review",
}
VALIDATION_STAGES = {"hypothesis", "piloted", "validated"}
OBJECTIVE_METRICS = {
    "revenue",
    "contribution_profit",
    "contribution_after_fixed_costs",
    "arpa",
    "active_customers",
}
GUARDRAILS = {
    "max_active_customer_loss_rate",
    "min_contribution_margin",
    "max_weighted_average_price_increase_rate",
    "max_manual_review_share",
    "capacity_units_per_period",
}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a nonnegative number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{path} must be finite")
    if number < 0:
        raise ValueError(f"{path} must be nonnegative")
    return number


def money_value(entry: object, path: str, currency: str) -> Decimal | None:
    value = _require_object(entry, path)
    evidence = value.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    if value.get("currency", currency) != currency:
        raise ValueError(f"{path}.currency must match top-level currency")
    amount = value.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path} unknown amount must be null")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required when evidence is known")
    return _decimal(amount, f"{path}.amount")


def scalar_value(
    entry: object,
    path: str,
    *,
    rate: bool = False,
    integer: bool = False,
) -> Decimal | None:
    value = _require_object(entry, path)
    evidence = value.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    raw = value.get("value")
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown value must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.value is required when evidence is known")
    number = _decimal(raw, f"{path}.value")
    if rate and number > 1:
        raise ValueError(f"{path} must be from 0 through 1")
    if integer and number != number.to_integral_value():
        raise ValueError(f"{path} must be a whole number")
    return number


def _validate_plan(plan: object, path: str, currency: str) -> tuple[str, str]:
    value = _require_object(plan, path)
    name = _require_nonempty_string(value.get("name"), f"{path}.name")
    _require_nonempty_string(value.get("package_label"), f"{path}.package_label")
    pricing = _require_object(value.get("pricing"), f"{path}.pricing")
    model = pricing.get("model")
    if model not in PRICING_MODELS:
        raise ValueError(f"{path}.pricing.model must be supported")
    required: dict[str, set[str]] = {
        "flat": {"flat_fee"},
        "base_plus_usage": {"base_fee", "included_usage_units", "price_per_excess_unit"},
        "percentage": {"percentage_rate"},
        "quoted": set(),
    }
    optional: dict[str, set[str]] = {
        "flat": set(),
        "base_plus_usage": {"minimum_fee", "maximum_fee"},
        "percentage": {"minimum_fee", "maximum_fee"},
        "quoted": set(),
    }
    fields = set(pricing) - {"model"}
    missing = required[model] - fields
    if missing:
        raise ValueError(f"{path}.pricing is missing required fields: {', '.join(sorted(missing))}")
    unsupported = fields - required[model] - optional[model]
    if unsupported:
        raise ValueError(f"{path}.pricing has unsupported pricing fields")
    for field in fields:
        if field in {"included_usage_units", "percentage_rate"}:
            scalar_value(
                pricing[field],
                f"{path}.pricing.{field}",
                rate=field == "percentage_rate",
            )
        else:
            money_value(pricing[field], f"{path}.pricing.{field}", currency)
    return name, model


def _validate_segment(
    segment: object,
    path: str,
    *,
    plans: dict[str, str],
    currency: str,
) -> str:
    value = _require_object(segment, path)
    name = _require_nonempty_string(value.get("name"), f"{path}.name")
    current_plan = _require_nonempty_string(value.get("current_plan"), f"{path}.current_plan")
    if current_plan not in plans:
        raise ValueError(f"segment {name} references unknown current plan")
    scalar_value(value.get("current_customers"), f"segment {name}.current_customers", integer=True)
    scalar_value(
        value.get("baseline_retention_rate"),
        f"segment {name}.baseline_retention_rate",
        rate=True,
    )
    scalar_value(
        value.get("baseline_new_customers_per_period"),
        f"segment {name}.baseline_new_customers_per_period",
        integer=True,
    )
    scalar_value(
        value.get("usage_units_per_customer_per_period"),
        f"segment {name}.usage_units_per_customer_per_period",
    )
    for field in (
        "billable_amount_per_customer_per_period",
        "fixed_variable_cost_per_customer_per_period",
        "variable_cost_per_usage_unit",
    ):
        money_value(value.get(field), f"segment {name}.{field}", currency)
    if plans[current_plan] == "quoted":
        if "current_quoted_charge_per_customer_per_period" not in value:
            raise ValueError(f"segment {name} requires a current quoted charge")
        money_value(
            value["current_quoted_charge_per_customer_per_period"],
            f"segment {name}.current_quoted_charge_per_customer_per_period",
            currency,
        )
    elif "current_quoted_charge_per_customer_per_period" in value:
        money_value(
            value["current_quoted_charge_per_customer_per_period"],
            f"segment {name}.current_quoted_charge_per_customer_per_period",
            currency,
        )
    return name


ASSIGNMENT_SCALARS = {
    "migration_share_within_horizon": "rate",
    "manual_review_share": "rate",
    "retention_rate_after_migration": "rate",
    "new_customer_multiplier": "scalar",
    "usage_multiplier": "scalar",
    "billable_amount_multiplier": "scalar",
    "variable_cost_multiplier": "scalar",
    "transition_discount_rate": "rate",
}


def _validate_assignment(
    assignment: object,
    path: str,
    *,
    segment_names: set[str],
    plans: dict[str, str],
    currency: str,
) -> str:
    value = _require_object(assignment, path)
    segment = _require_nonempty_string(value.get("segment"), f"{path}.segment")
    if segment not in segment_names:
        raise ValueError(f"{path} references unknown segment")
    target_plan = _require_nonempty_string(value.get("target_plan"), f"{path}.target_plan")
    if target_plan not in plans:
        raise ValueError(f"{path} references unknown target plan")
    policy = value.get("migration_policy")
    if policy not in MIGRATION_POLICIES:
        raise ValueError(f"{path}.migration_policy must be supported")
    parsed: dict[str, Decimal | None] = {}
    for field, kind in ASSIGNMENT_SCALARS.items():
        parsed[field] = scalar_value(value.get(field), f"{path}.{field}", rate=kind == "rate")
    migration = parsed["migration_share_within_horizon"]
    review = parsed["manual_review_share"]
    if migration is not None and review is not None and migration + review > 1:
        raise ValueError("migration and manual-review shares must sum to at most 1")
    if policy == "grandfathered" and migration != 0:
        raise ValueError("grandfathered requires zero migration share")
    if policy == "manual_review" and (review is None or review == 0):
        raise ValueError("manual_review requires a positive manual-review share")
    if plans[target_plan] == "quoted":
        if "quoted_charge_per_customer_per_period" not in value:
            raise ValueError(f"{path} requires a quoted charge")
        money_value(
            value["quoted_charge_per_customer_per_period"],
            f"{path}.quoted_charge_per_customer_per_period",
            currency,
        )
    elif "quoted_charge_per_customer_per_period" in value:
        money_value(
            value["quoted_charge_per_customer_per_period"],
            f"{path}.quoted_charge_per_customer_per_period",
            currency,
        )
    return segment


def validate(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "payload")
    if data.get("mode") not in MODES:
        raise ValueError("mode must be recurring, transactional, or service_project")
    raw_date = data.get("as_of_date")
    if not isinstance(raw_date, str):
        raise ValueError("as_of_date must be an ISO date")
    try:
        date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError("as_of_date must be an ISO date") from exc
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter code")
    if data.get("analysis_period") not in PERIOD_UNITS:
        raise ValueError("analysis_period must be week, month, quarter, or year")
    scalar_value(
        data.get("evaluation_horizon_periods"),
        "evaluation_horizon_periods",
        integer=True,
    )
    _require_nonempty_string(data.get("usage_unit_name"), "usage_unit_name")
    objective = data.get("objective")
    if objective is not None:
        objective_value = _require_object(objective, "objective")
        if objective_value.get("metric") not in OBJECTIVE_METRICS:
            raise ValueError("unsupported objective metric")
    guardrails = _require_object(data.get("guardrails", {}), "guardrails")
    unsupported_guardrails = set(guardrails) - GUARDRAILS
    if unsupported_guardrails:
        raise ValueError("guardrails contain unsupported fields")
    for field, entry in guardrails.items():
        scalar_value(entry, f"guardrails.{field}", rate=field != "capacity_units_per_period")
    money_value(data.get("current_fixed_costs_per_period"), "current_fixed_costs_per_period", currency)

    plans_input = data.get("plans")
    if not isinstance(plans_input, list) or not plans_input:
        raise ValueError("plans must be a nonempty list")
    plans: dict[str, str] = {}
    for index, plan in enumerate(plans_input):
        name, model = _validate_plan(plan, f"plan {index}", currency)
        if name in plans:
            raise ValueError(f"duplicate plan name {name}")
        plans[name] = model

    segments_input = data.get("segments")
    if not isinstance(segments_input, list) or not segments_input:
        raise ValueError("segments must be a nonempty list")
    segment_names: set[str] = set()
    for index, segment in enumerate(segments_input):
        name = _validate_segment(
            segment,
            f"segment {index}",
            plans=plans,
            currency=currency,
        )
        if name in segment_names:
            raise ValueError(f"duplicate segment name {name}")
        segment_names.add(name)

    proposals_input = data.get("proposals")
    if not isinstance(proposals_input, list) or not proposals_input:
        raise ValueError("proposals must be a nonempty list")
    proposal_names: set[str] = set()
    for index, raw_proposal in enumerate(proposals_input):
        proposal = _require_object(raw_proposal, f"proposal {index}")
        name = _require_nonempty_string(proposal.get("name"), f"proposal {index}.name")
        if name in proposal_names:
            raise ValueError(f"duplicate proposal name {name}")
        proposal_names.add(name)
        if proposal.get("validation_stage") not in VALIDATION_STAGES:
            raise ValueError(f"proposal {name}.validation_stage must be supported")
        summary = proposal.get("change_summary")
        if not isinstance(summary, list) or any(not isinstance(item, str) for item in summary):
            raise ValueError(f"proposal {name}.change_summary must be a string list")
        money_value(
            proposal.get("incremental_fixed_costs_per_period"),
            f"proposal {name}.incremental_fixed_costs_per_period",
            currency,
        )
        money_value(
            proposal.get("one_time_implementation_costs"),
            f"proposal {name}.one_time_implementation_costs",
            currency,
        )
        assignments = proposal.get("assignments")
        if not isinstance(assignments, list):
            raise ValueError(f"proposal {name}.assignments must be a list")
        assigned: set[str] = set()
        for assignment_index, assignment in enumerate(assignments):
            segment = _validate_assignment(
                assignment,
                f"proposal {name}.assignment {assignment_index}",
                segment_names=segment_names,
                plans=plans,
                currency=currency,
            )
            if segment in assigned:
                raise ValueError(f"proposal {name} has duplicate assignment for {segment}")
            assigned.add(segment)
        if assigned != segment_names:
            raise ValueError(f"proposal {name} must have exactly one assignment per segment")

    sensitivity_cases = data.get("sensitivity_cases", [])
    if not isinstance(sensitivity_cases, list):
        raise ValueError("sensitivity_cases must be a list")
    return data


def calculate_charge(
    plan: dict[str, object],
    *,
    usage: Decimal | None,
    billable_amount: Decimal | None,
    quoted_charge: Decimal | None,
    currency: str,
) -> Decimal | str:
    pricing = plan["pricing"]
    model = pricing["model"]
    if model == "flat":
        amount = money_value(pricing["flat_fee"], "pricing.flat_fee", currency)
        return amount if amount is not None else "indeterminate"
    if model == "quoted":
        return quoted_charge if quoted_charge is not None else "indeterminate"
    if model == "base_plus_usage":
        base = money_value(pricing["base_fee"], "pricing.base_fee", currency)
        included = scalar_value(pricing["included_usage_units"], "pricing.included_usage_units")
        excess_price = money_value(
            pricing["price_per_excess_unit"], "pricing.price_per_excess_unit", currency
        )
        if usage is None or base is None or included is None or excess_price is None:
            return "indeterminate"
        raw_charge = base + max(Decimal("0"), usage - included) * excess_price
    else:
        rate = scalar_value(pricing["percentage_rate"], "pricing.percentage_rate", rate=True)
        if billable_amount is None or rate is None:
            return "indeterminate"
        raw_charge = billable_amount * rate
    for field, comparator in (("minimum_fee", max), ("maximum_fee", min)):
        if field in pricing:
            bound = money_value(pricing[field], f"pricing.{field}", currency)
            if bound is None:
                return "indeterminate"
            raw_charge = comparator(raw_charge, bound)
    return raw_charge


def calculate(payload: dict[str, object]) -> dict[str, object]:
    data = validate(payload)
    return {
        "mode": data["mode"],
        "as_of_date": data["as_of_date"],
        "currency": data["currency"],
        "analysis_period": data["analysis_period"],
        "usage_unit_name": data["usage_unit_name"],
        "current": {},
        "proposals": [],
        "sensitivity_cases": [],
    }


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file path, or - for standard input")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = handle.read()
        result = calculate(json.loads(raw, parse_float=Decimal))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
