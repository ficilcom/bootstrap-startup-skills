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


def _input_quality(value: object, path: str = "") -> tuple[list[str], bool]:
    missing: list[str] = []
    estimate_based = False
    if isinstance(value, dict):
        if value.get("evidence") in EVIDENCE_STATES:
            estimate_based = value.get("evidence") == "estimated"
            raw = value.get("amount", value.get("value"))
            if value.get("evidence") == "unknown" and raw is None:
                missing.append(path)
        else:
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                child_missing, child_estimate = _input_quality(child, child_path)
                missing.extend(child_missing)
                estimate_based = estimate_based or child_estimate
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_missing, child_estimate = _input_quality(child, f"{path}[{index}]")
            missing.extend(child_missing)
            estimate_based = estimate_based or child_estimate
    return missing, estimate_based


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def _all_numeric(values: list[object]) -> bool:
    return all(_is_numeric(value) for value in values)


def _metric_totals(
    segment_results: list[dict[str, object]],
    field: str,
) -> Decimal | str:
    values = [segment[field] for segment in segment_results]
    return sum(values, Decimal("0")) if _all_numeric(values) else "indeterminate"


def _capacity_status(
    total_usage: Decimal | str,
    guardrails: dict[str, object],
) -> tuple[Decimal | None, str]:
    if "capacity_units_per_period" not in guardrails:
        return None, "unassessed"
    capacity = scalar_value(
        guardrails["capacity_units_per_period"],
        "guardrails.capacity_units_per_period",
    )
    if capacity is None or not isinstance(total_usage, Decimal):
        return capacity, "unassessed"
    return capacity, "beyond_capacity" if total_usage > capacity else "within_capacity"


def _plan_maps(data: dict[str, object]) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    plans = {plan["name"]: plan for plan in data["plans"]}
    segments = {segment["name"]: segment for segment in data["segments"]}
    return plans, segments


def _current_segment(
    segment: dict[str, object],
    *,
    plan: dict[str, object],
    currency: str,
) -> dict[str, object]:
    name = segment["name"]
    current_customers = scalar_value(
        segment["current_customers"], f"segments.{name}.current_customers"
    )
    retention = scalar_value(
        segment["baseline_retention_rate"],
        f"segments.{name}.baseline_retention_rate",
        rate=True,
    )
    new_customers = scalar_value(
        segment["baseline_new_customers_per_period"],
        f"segments.{name}.baseline_new_customers_per_period",
    )
    usage = scalar_value(
        segment["usage_units_per_customer_per_period"],
        f"segments.{name}.usage_units_per_customer_per_period",
    )
    billable_amount = money_value(
        segment["billable_amount_per_customer_per_period"],
        f"segments.{name}.billable_amount_per_customer_per_period",
        currency,
    )
    quoted_charge = (
        money_value(
            segment["current_quoted_charge_per_customer_per_period"],
            f"segments.{name}.current_quoted_charge_per_customer_per_period",
            currency,
        )
        if "current_quoted_charge_per_customer_per_period" in segment
        else None
    )
    fixed_variable_cost = money_value(
        segment["fixed_variable_cost_per_customer_per_period"],
        f"segments.{name}.fixed_variable_cost_per_customer_per_period",
        currency,
    )
    usage_cost = money_value(
        segment["variable_cost_per_usage_unit"],
        f"segments.{name}.variable_cost_per_usage_unit",
        currency,
    )
    current_charge = calculate_charge(
        plan,
        usage=usage,
        billable_amount=billable_amount,
        quoted_charge=quoted_charge,
        currency=currency,
    )
    retained: Decimal | str = (
        current_customers * retention
        if current_customers is not None and retention is not None
        else "indeterminate"
    )
    active: Decimal | str = (
        retained + new_customers
        if isinstance(retained, Decimal) and new_customers is not None
        else "indeterminate"
    )
    cost_per_customer: Decimal | str = (
        fixed_variable_cost + usage_cost * usage
        if fixed_variable_cost is not None and usage_cost is not None and usage is not None
        else "indeterminate"
    )
    revenue: Decimal | str = (
        active * current_charge
        if isinstance(active, Decimal) and isinstance(current_charge, Decimal)
        else "indeterminate"
    )
    contribution: Decimal | str = (
        revenue - active * cost_per_customer
        if isinstance(revenue, Decimal)
        and isinstance(active, Decimal)
        and isinstance(cost_per_customer, Decimal)
        else "indeterminate"
    )
    total_usage: Decimal | str = (
        active * usage if isinstance(active, Decimal) and usage is not None else "indeterminate"
    )
    return {
        "name": name,
        "current_plan": segment["current_plan"],
        "current_charge": current_charge,
        "retained_existing_customers": retained,
        "new_customers": new_customers,
        "active_customers": active,
        "usage_units_per_customer": usage,
        "cost_per_customer": cost_per_customer,
        "revenue": revenue,
        "contribution_profit": contribution,
        "total_usage_units": total_usage,
    }


def calculate_current(data: dict[str, object]) -> dict[str, object]:
    plans, _ = _plan_maps(data)
    currency = data["currency"]
    segment_results = [
        _current_segment(segment, plan=plans[segment["current_plan"]], currency=currency)
        for segment in data["segments"]
    ]
    active = _metric_totals(segment_results, "active_customers")
    revenue = _metric_totals(segment_results, "revenue")
    contribution = _metric_totals(segment_results, "contribution_profit")
    total_usage = _metric_totals(segment_results, "total_usage_units")
    fixed = money_value(
        data["current_fixed_costs_per_period"],
        "current_fixed_costs_per_period",
        currency,
    )
    after_fixed: Decimal | str = (
        contribution - fixed
        if isinstance(contribution, Decimal) and fixed is not None
        else "indeterminate"
    )
    if not isinstance(revenue, Decimal) or not isinstance(contribution, Decimal):
        contribution_margin: Decimal | str = "indeterminate"
    elif revenue == 0:
        contribution_margin = "indeterminate_zero_revenue"
    else:
        contribution_margin = contribution / revenue
    if not isinstance(active, Decimal) or not isinstance(revenue, Decimal):
        arpa: Decimal | str = "indeterminate"
    elif active == 0:
        arpa = "indeterminate_zero_active_customers"
    else:
        arpa = revenue / active
    capacity, capacity_status = _capacity_status(total_usage, data.get("guardrails", {}))
    missing, estimate_based = _input_quality(
        {
            "segments": data["segments"],
            "current_fixed_costs_per_period": data["current_fixed_costs_per_period"],
        }
    )
    return {
        "estimate_based": estimate_based,
        "missing_inputs": missing,
        "segments": segment_results,
        "metrics": {
            "active_customers": active,
            "revenue": revenue,
            "contribution_profit": contribution,
            "contribution_margin": contribution_margin,
            "current_fixed_costs_per_period": fixed,
            "contribution_after_fixed_costs": after_fixed,
            "arpa": arpa,
            "total_usage_units": total_usage,
            "capacity_units_per_period": capacity,
            "capacity_status": capacity_status,
        },
    }


def _proposal_segment(
    segment: dict[str, object],
    assignment: dict[str, object],
    *,
    plans: dict[str, dict[str, object]],
    current_segment: dict[str, object],
    currency: str,
) -> dict[str, object]:
    name = segment["name"]
    current_customers = scalar_value(
        segment["current_customers"], f"segments.{name}.current_customers"
    )
    baseline_retention = scalar_value(
        segment["baseline_retention_rate"],
        f"segments.{name}.baseline_retention_rate",
        rate=True,
    )
    baseline_new = scalar_value(
        segment["baseline_new_customers_per_period"],
        f"segments.{name}.baseline_new_customers_per_period",
    )
    baseline_usage = scalar_value(
        segment["usage_units_per_customer_per_period"],
        f"segments.{name}.usage_units_per_customer_per_period",
    )
    baseline_billable = money_value(
        segment["billable_amount_per_customer_per_period"],
        f"segments.{name}.billable_amount_per_customer_per_period",
        currency,
    )
    fixed_variable_cost = money_value(
        segment["fixed_variable_cost_per_customer_per_period"],
        f"segments.{name}.fixed_variable_cost_per_customer_per_period",
        currency,
    )
    usage_cost = money_value(
        segment["variable_cost_per_usage_unit"],
        f"segments.{name}.variable_cost_per_usage_unit",
        currency,
    )
    parsed = {
        field: scalar_value(
            assignment[field],
            f"assignments.{name}.{field}",
            rate=kind == "rate",
        )
        for field, kind in ASSIGNMENT_SCALARS.items()
    }
    migration_share = parsed["migration_share_within_horizon"]
    review_share = parsed["manual_review_share"]
    migration_retention = parsed["retention_rate_after_migration"]
    new_multiplier = parsed["new_customer_multiplier"]
    usage_multiplier = parsed["usage_multiplier"]
    billable_multiplier = parsed["billable_amount_multiplier"]
    cost_multiplier = parsed["variable_cost_multiplier"]
    discount = parsed["transition_discount_rate"]

    migration_cohort: Decimal | str = (
        current_customers * migration_share
        if current_customers is not None and migration_share is not None
        else "indeterminate"
    )
    manual_review: Decimal | str = (
        current_customers * review_share
        if current_customers is not None and review_share is not None
        else "indeterminate"
    )
    migrated_retained: Decimal | str = (
        migration_cohort * migration_retention
        if isinstance(migration_cohort, Decimal) and migration_retention is not None
        else "indeterminate"
    )
    migration_losses: Decimal | str = (
        migration_cohort * (Decimal("1") - migration_retention)
        if isinstance(migration_cohort, Decimal) and migration_retention is not None
        else "indeterminate"
    )
    legacy_retained: Decimal | str = (
        (current_customers - migration_cohort) * baseline_retention
        if current_customers is not None
        and isinstance(migration_cohort, Decimal)
        and baseline_retention is not None
        else "indeterminate"
    )
    new_customers: Decimal | str = (
        baseline_new * new_multiplier
        if baseline_new is not None and new_multiplier is not None
        else "indeterminate"
    )
    active: Decimal | str = (
        migrated_retained + legacy_retained + new_customers
        if _all_numeric([migrated_retained, legacy_retained, new_customers])
        else "indeterminate"
    )
    proposal_usage: Decimal | str = (
        baseline_usage * usage_multiplier
        if baseline_usage is not None and usage_multiplier is not None
        else "indeterminate"
    )
    proposal_billable: Decimal | str = (
        baseline_billable * billable_multiplier
        if baseline_billable is not None and billable_multiplier is not None
        else "indeterminate"
    )
    quoted_charge = (
        money_value(
            assignment["quoted_charge_per_customer_per_period"],
            f"assignments.{name}.quoted_charge_per_customer_per_period",
            currency,
        )
        if "quoted_charge_per_customer_per_period" in assignment
        else None
    )
    target_charge = calculate_charge(
        plans[assignment["target_plan"]],
        usage=proposal_usage if isinstance(proposal_usage, Decimal) else None,
        billable_amount=proposal_billable if isinstance(proposal_billable, Decimal) else None,
        quoted_charge=quoted_charge,
        currency=currency,
    )
    effective_migrated_charge: Decimal | str = (
        target_charge * (Decimal("1") - discount)
        if isinstance(target_charge, Decimal) and discount is not None
        else "indeterminate"
    )
    current_charge = current_segment["current_charge"]
    legacy_revenue: Decimal | str = (
        legacy_retained * current_charge
        if isinstance(legacy_retained, Decimal) and isinstance(current_charge, Decimal)
        else "indeterminate"
    )
    migrated_revenue: Decimal | str = (
        migrated_retained * effective_migrated_charge
        if isinstance(migrated_retained, Decimal)
        and isinstance(effective_migrated_charge, Decimal)
        else "indeterminate"
    )
    new_revenue: Decimal | str = (
        new_customers * target_charge
        if isinstance(new_customers, Decimal) and isinstance(target_charge, Decimal)
        else "indeterminate"
    )
    revenue: Decimal | str = (
        legacy_revenue + migrated_revenue + new_revenue
        if _all_numeric([legacy_revenue, migrated_revenue, new_revenue])
        else "indeterminate"
    )
    proposal_cost: Decimal | str = (
        (fixed_variable_cost + usage_cost * proposal_usage) * cost_multiplier
        if fixed_variable_cost is not None
        and usage_cost is not None
        and isinstance(proposal_usage, Decimal)
        and cost_multiplier is not None
        else "indeterminate"
    )
    contribution: Decimal | str = (
        revenue - active * proposal_cost
        if isinstance(revenue, Decimal)
        and isinstance(active, Decimal)
        and isinstance(proposal_cost, Decimal)
        else "indeterminate"
    )
    total_usage: Decimal | str = (
        active * proposal_usage
        if isinstance(active, Decimal) and isinstance(proposal_usage, Decimal)
        else "indeterminate"
    )
    return {
        "name": name,
        "current_plan": segment["current_plan"],
        "target_plan": assignment["target_plan"],
        "migration_policy": assignment["migration_policy"],
        "retention_rate_after_migration": migration_retention,
        "migration_cohort": migration_cohort,
        "migrated_retained_customers": migrated_retained,
        "migration_losses": migration_losses,
        "legacy_retained_customers": legacy_retained,
        "new_customers": new_customers,
        "manual_review_customers": manual_review,
        "current_charge": current_charge,
        "target_new_customer_charge": target_charge,
        "effective_migrated_charge": effective_migrated_charge,
        "proposal_usage_units_per_customer": proposal_usage,
        "proposal_variable_cost_per_customer": proposal_cost,
        "active_customers": active,
        "legacy_revenue": legacy_revenue,
        "migrated_revenue": migrated_revenue,
        "new_revenue": new_revenue,
        "revenue": revenue,
        "contribution_profit": contribution,
        "total_usage_units": total_usage,
    }


def _numeric_deltas(
    proposal_metrics: dict[str, object],
    current_metrics: dict[str, object],
) -> dict[str, Decimal]:
    fields = {
        "active_customers",
        "revenue",
        "contribution_profit",
        "contribution_after_fixed_costs",
        "arpa",
        "total_usage_units",
    }
    return {
        field: proposal_metrics[field] - current_metrics[field]
        for field in fields
        if _is_numeric(proposal_metrics[field]) and _is_numeric(current_metrics[field])
    }


def calculate_proposal(
    data: dict[str, object],
    proposal: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    plans, segments = _plan_maps(data)
    current_segments = {segment["name"]: segment for segment in current["segments"]}
    assignments = {assignment["segment"]: assignment for assignment in proposal["assignments"]}
    segment_results = [
        _proposal_segment(
            segment,
            assignments[name],
            plans=plans,
            current_segment=current_segments[name],
            currency=data["currency"],
        )
        for name, segment in segments.items()
    ]
    active = _metric_totals(segment_results, "active_customers")
    revenue = _metric_totals(segment_results, "revenue")
    contribution = _metric_totals(segment_results, "contribution_profit")
    total_usage = _metric_totals(segment_results, "total_usage_units")
    current_fixed = money_value(
        data["current_fixed_costs_per_period"],
        "current_fixed_costs_per_period",
        data["currency"],
    )
    incremental_fixed = money_value(
        proposal["incremental_fixed_costs_per_period"],
        f"proposals.{proposal['name']}.incremental_fixed_costs_per_period",
        data["currency"],
    )
    one_time = money_value(
        proposal["one_time_implementation_costs"],
        f"proposals.{proposal['name']}.one_time_implementation_costs",
        data["currency"],
    )
    after_fixed: Decimal | str = (
        contribution - current_fixed - incremental_fixed
        if isinstance(contribution, Decimal)
        and current_fixed is not None
        and incremental_fixed is not None
        else "indeterminate"
    )
    if not isinstance(revenue, Decimal) or not isinstance(contribution, Decimal):
        contribution_margin: Decimal | str = "indeterminate"
    elif revenue == 0:
        contribution_margin = "indeterminate_zero_revenue"
    else:
        contribution_margin = contribution / revenue
    if not isinstance(active, Decimal) or not isinstance(revenue, Decimal):
        arpa: Decimal | str = "indeterminate"
    elif active == 0:
        arpa = "indeterminate_zero_active_customers"
    else:
        arpa = revenue / active
    capacity, capacity_status = _capacity_status(total_usage, data.get("guardrails", {}))
    metrics = {
        "active_customers": active,
        "revenue": revenue,
        "contribution_profit": contribution,
        "contribution_margin": contribution_margin,
        "current_fixed_costs_per_period": current_fixed,
        "incremental_fixed_costs_per_period": incremental_fixed,
        "contribution_after_fixed_costs": after_fixed,
        "arpa": arpa,
        "total_usage_units": total_usage,
        "capacity_units_per_period": capacity,
        "capacity_status": capacity_status,
    }
    missing, estimate_based = _input_quality(
        {"proposal": proposal, "segments": data["segments"]}
    )
    return {
        "name": proposal["name"],
        "validation_stage": proposal["validation_stage"],
        "change_summary": proposal["change_summary"],
        "estimate_based": estimate_based,
        "missing_inputs": missing,
        "segments": segment_results,
        "metrics": metrics,
        "deltas": _numeric_deltas(metrics, current["metrics"]),
        "one_time_implementation_costs": one_time,
    }


def calculate(payload: dict[str, object]) -> dict[str, object]:
    data = validate(payload)
    current = calculate_current(data)
    proposals = [calculate_proposal(data, proposal, current) for proposal in data["proposals"]]
    return {
        "mode": data["mode"],
        "as_of_date": data["as_of_date"],
        "currency": data["currency"],
        "analysis_period": data["analysis_period"],
        "usage_unit_name": data["usage_unit_name"],
        "current": current,
        "proposals": proposals,
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
