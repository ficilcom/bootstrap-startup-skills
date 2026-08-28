#!/usr/bin/env python3
"""Calculate unit economics scenarios from an anonymous JSON model."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"recurring", "transactional", "service_project"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
CAC_BASES = {"paid", "blended", "fully_loaded", "marginal"}
LTV_METHODS = {"observed_cohort", "fixed_horizon", "constant_retention"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
REQUIRED_DRIVERS = {
    "price_per_unit",
    "cogs_per_unit",
    "other_variable_cost_per_unit",
    "volume_units",
    "fixed_costs",
    "new_customers",
}
OPTIONAL_DRIVERS = {"units_per_customer_per_period", "capacity_units"}


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
    entry_currency = value.get("currency", currency)
    if entry_currency != currency:
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
        field = path.rsplit(".", 1)[-1]
        raise ValueError(f"{field} must be a whole number")
    return number


def _validate_drivers(
    value: object,
    path: str,
    currency: str,
    *,
    unit_is_discrete: bool,
) -> None:
    drivers = _require_object(value, path)
    keys = set(drivers)
    if not REQUIRED_DRIVERS <= keys:
        missing = ", ".join(sorted(REQUIRED_DRIVERS - keys))
        raise ValueError(f"{path} is missing required drivers: {missing}")
    unexpected = keys - REQUIRED_DRIVERS - OPTIONAL_DRIVERS
    if unexpected:
        raise ValueError(f"{path} has unsupported drivers: {', '.join(sorted(unexpected))}")
    for field in ("price_per_unit", "cogs_per_unit", "other_variable_cost_per_unit", "fixed_costs"):
        money_value(drivers[field], f"{path}.{field}", currency)
    scalar_value(
        drivers["volume_units"],
        f"{path}.volume_units",
        integer=unit_is_discrete,
    )
    scalar_value(drivers["new_customers"], f"{path}.new_customers", integer=True)
    if "units_per_customer_per_period" in drivers:
        scalar_value(
            drivers["units_per_customer_per_period"],
            f"{path}.units_per_customer_per_period",
        )
    if "capacity_units" in drivers:
        scalar_value(
            drivers["capacity_units"],
            f"{path}.capacity_units",
            integer=unit_is_discrete,
        )


def _validate_acquisition(value: object, path: str, currency: str) -> None:
    acquisition = _require_object(value, path)
    basis = acquisition.get("decision_cac_basis")
    if basis not in CAC_BASES:
        raise ValueError(f"{path}.decision_cac_basis must be a supported CAC basis")
    for field in (
        "decision_cac_scope_complete",
        "selected_pool_matches_customer_cohort",
        "selected_pool_included_in_fixed_costs",
    ):
        if not isinstance(acquisition.get(field), bool):
            raise ValueError(f"{field} must be a boolean")
    costs = _require_object(acquisition.get("costs"), f"{path}.costs")
    if not costs or any(key not in CAC_BASES for key in costs):
        raise ValueError(f"{path}.costs must use supported CAC bases")
    for cost_basis, entry in costs.items():
        money_value(entry, f"{path}.costs.{cost_basis}", currency)
    if basis not in costs:
        raise ValueError("decision_cac_basis must be present in acquisition costs")
    if "marginal" in costs:
        if "marginal_new_customers" not in acquisition:
            raise ValueError("marginal_new_customers is required for marginal CAC")
        scalar_value(
            acquisition["marginal_new_customers"],
            f"{path}.marginal_new_customers",
            integer=True,
        )


def _validate_ltv_model(
    value: object,
    path: str,
    *,
    mode: str,
    analysis_period: str,
    currency: str,
) -> None:
    model = _require_object(value, path)
    method = model.get("method")
    if method not in LTV_METHODS:
        raise ValueError(f"{path}.method must be a supported LTV method")
    if model.get("period_unit") != analysis_period:
        raise ValueError(f"{path}.period_unit must match analysis_period")
    if method == "constant_retention":
        if mode != "recurring":
            raise ValueError("constant_retention is only valid for recurring mode")
        scalar_value(
            model.get("churn_rate_per_period"),
            f"{path}.churn_rate_per_period",
            rate=True,
        )
    elif method == "fixed_horizon":
        scalar_value(
            model.get("expected_units_per_customer_within_horizon"),
            f"{path}.expected_units_per_customer_within_horizon",
        )
        scalar_value(
            model.get("horizon_periods"),
            f"{path}.horizon_periods",
            integer=True,
        )
    else:
        scalar_value(
            model.get("cohort_customers"),
            f"{path}.cohort_customers",
            integer=True,
        )
        contributions = model.get("contribution_totals_by_period")
        if not isinstance(contributions, list) or not contributions:
            raise ValueError(f"{path}.contribution_totals_by_period must be a nonempty list")
        for index, entry in enumerate(contributions):
            money_value(entry, f"{path}.contribution_totals_by_period[{index}]", currency)


def _validate_scenario(
    value: object,
    path: str,
    *,
    mode: str,
    analysis_period: str,
    currency: str,
    unit_is_discrete: bool,
) -> str:
    scenario = _require_object(value, path)
    name = _require_nonempty_string(scenario.get("name"), f"{path}.name")
    _validate_drivers(
        scenario.get("drivers"),
        f"scenario {name}.drivers",
        currency,
        unit_is_discrete=unit_is_discrete,
    )
    _validate_acquisition(scenario.get("acquisition"), f"scenario {name}.acquisition", currency)
    _validate_ltv_model(
        scenario.get("ltv_model"),
        f"scenario {name}.ltv_model",
        mode=mode,
        analysis_period=analysis_period,
        currency=currency,
    )
    targets = scenario.get("targets", {})
    targets = _require_object(targets, f"scenario {name}.targets")
    if set(targets) - {"max_payback_periods"}:
        raise ValueError(f"scenario {name}.targets contains unsupported fields")
    if "max_payback_periods" in targets:
        scalar_value(
            targets["max_payback_periods"],
            f"scenario {name}.targets.max_payback_periods",
        )
    return name


def _allowed_sensitivity_paths(source: dict[str, object]) -> set[str]:
    paths = {
        *(f"drivers.{field}" for field in REQUIRED_DRIVERS | OPTIONAL_DRIVERS),
        *(f"acquisition.costs.{basis}" for basis in CAC_BASES),
        "acquisition.marginal_new_customers",
        "targets.max_payback_periods",
    }
    method = source["ltv_model"]["method"]
    if method == "constant_retention":
        paths.add("ltv_model.churn_rate_per_period")
    elif method == "fixed_horizon":
        paths.update(
            {
                "ltv_model.expected_units_per_customer_within_horizon",
                "ltv_model.horizon_periods",
            }
        )
    else:
        paths.update(
            {
                "ltv_model.cohort_customers",
                "ltv_model.contribution_totals_by_period",
            }
        )
    return paths


def _apply_overrides(
    source: dict[str, object],
    overrides: dict[str, object],
) -> dict[str, object]:
    result = copy.deepcopy(source)
    for path, replacement in overrides.items():
        parts = path.split(".")
        current: dict[str, object] = result
        for part in parts[:-1]:
            child = current.get(part)
            if child is None:
                child = {}
                current[part] = child
            current = _require_object(child, path)
        current[parts[-1]] = copy.deepcopy(replacement)
    return result


def validate(payload: object) -> dict[str, Any]:
    data = _require_object(payload, "payload")
    mode = data.get("mode")
    if mode not in MODES:
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
    analysis_period = data.get("analysis_period")
    if analysis_period not in PERIOD_UNITS:
        raise ValueError("analysis_period must be week, month, quarter, or year")
    _require_nonempty_string(data.get("unit_name"), "unit_name")
    if not isinstance(data.get("unit_is_discrete"), bool):
        raise ValueError("unit_is_discrete must be a boolean")
    _require_nonempty_string(data.get("revenue_basis"), "revenue_basis")

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a nonempty list")
    names: set[str] = set()
    scenarios_by_name: dict[str, dict[str, object]] = {}
    for index, scenario in enumerate(scenarios):
        name = _validate_scenario(
            scenario,
            f"scenario {index}",
            mode=mode,
            analysis_period=analysis_period,
            currency=currency,
            unit_is_discrete=data["unit_is_discrete"],
        )
        if name in names:
            raise ValueError(f"duplicate scenario name {name}")
        names.add(name)
        scenarios_by_name[name] = scenario
    if "base" not in names:
        raise ValueError("scenarios must include base")

    sensitivity_cases = data.get("sensitivity_cases", [])
    if not isinstance(sensitivity_cases, list):
        raise ValueError("sensitivity_cases must be a list")
    sensitivity_names: set[str] = set()
    for index, raw_case in enumerate(sensitivity_cases):
        case = _require_object(raw_case, f"sensitivity case {index}")
        unexpected = set(case) - {"name", "source_scenario", "overrides"}
        if unexpected:
            raise ValueError(
                f"sensitivity case {index} contains unsupported fields: "
                f"{', '.join(sorted(unexpected))}"
            )
        name = _require_nonempty_string(case.get("name"), f"sensitivity case {index}.name")
        if name in sensitivity_names:
            raise ValueError(f"duplicate sensitivity name {name}")
        sensitivity_names.add(name)
        source_name = _require_nonempty_string(
            case.get("source_scenario"),
            f"sensitivity case {name}.source_scenario",
        )
        if source_name not in scenarios_by_name:
            raise ValueError(f"sensitivity case {name} references unknown source scenario")
        overrides = _require_object(case.get("overrides"), f"sensitivity case {name}.overrides")
        if not overrides:
            raise ValueError(f"sensitivity case {name}.overrides must not be empty")
        allowed_paths = _allowed_sensitivity_paths(scenarios_by_name[source_name])
        for path in overrides:
            if path not in allowed_paths:
                raise ValueError(f"unsupported sensitivity override path {path}")
        modified = _apply_overrides(scenarios_by_name[source_name], overrides)
        modified["name"] = name
        _validate_scenario(
            modified,
            f"sensitivity case {name}",
            mode=mode,
            analysis_period=analysis_period,
            currency=currency,
            unit_is_discrete=data["unit_is_discrete"],
        )
    return data


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


def _known(*values: Decimal | None) -> bool:
    return all(value is not None for value in values)


def _calculate_cac(
    scenario: dict[str, object],
    *,
    currency: str,
) -> tuple[dict[str, object], Decimal | str]:
    drivers = scenario["drivers"]
    acquisition = scenario["acquisition"]
    new_customers = scalar_value(drivers["new_customers"], "drivers.new_customers")
    marginal_customers = (
        scalar_value(
            acquisition["marginal_new_customers"],
            "acquisition.marginal_new_customers",
        )
        if "marginal_new_customers" in acquisition
        else None
    )
    by_basis: dict[str, Decimal | str] = {}
    for basis, entry in acquisition["costs"].items():
        pool = money_value(entry, f"acquisition.costs.{basis}", currency)
        denominator = marginal_customers if basis == "marginal" else new_customers
        if pool is None or denominator is None:
            value: Decimal | str = "indeterminate"
        elif denominator == 0:
            value = (
                "indeterminate_zero_marginal_new_customers"
                if basis == "marginal"
                else "indeterminate_zero_new_customers"
            )
        else:
            value = pool / denominator
        by_basis[basis] = value

    selected_basis = acquisition["decision_cac_basis"]
    selected_cac = by_basis[selected_basis]
    return (
        {
            "by_basis": by_basis,
            "selected_basis": selected_basis,
            "selected_cac": selected_cac,
            "scope_complete": acquisition["decision_cac_scope_complete"],
            "customer_cohort_aligned": acquisition["selected_pool_matches_customer_cohort"],
            "selected_pool_included_in_fixed_costs": acquisition[
                "selected_pool_included_in_fixed_costs"
            ],
        },
        selected_cac,
    )


def _calculate_customer_economics(
    scenario: dict[str, object],
    *,
    contribution: Decimal | str,
    selected_cac: Decimal | str,
    currency: str,
) -> dict[str, object]:
    drivers = scenario["drivers"]
    units_per_customer = (
        scalar_value(
            drivers["units_per_customer_per_period"],
            "drivers.units_per_customer_per_period",
        )
        if "units_per_customer_per_period" in drivers
        else None
    )
    customer_contribution: Decimal | str = (
        contribution * units_per_customer
        if isinstance(contribution, Decimal) and units_per_customer is not None
        else "indeterminate"
    )

    model = scenario["ltv_model"]
    method = model["method"]
    horizon: int | str | None = None
    expected_lifetime: Decimal | str | None = None

    if method == "observed_cohort":
        cohort_customers = scalar_value(model["cohort_customers"], "ltv_model.cohort_customers")
        totals = [
            money_value(entry, f"ltv_model.contribution_totals_by_period[{index}]", currency)
            for index, entry in enumerate(model["contribution_totals_by_period"])
        ]
        horizon = len(totals)
        if cohort_customers is None or any(total is None for total in totals):
            ltv: Decimal | str = "indeterminate"
            payback: Decimal | int | str = "indeterminate"
        elif cohort_customers == 0:
            ltv = "indeterminate_zero_cohort_customers"
            payback = "indeterminate_zero_cohort_customers"
        else:
            known_totals = [total for total in totals if isinstance(total, Decimal)]
            ltv = sum(known_totals, Decimal("0")) / cohort_customers
            if not isinstance(selected_cac, Decimal):
                payback = "indeterminate"
            elif selected_cac == 0:
                payback = 0
            else:
                cumulative = Decimal("0")
                payback = "not_observed_within_horizon"
                for period, total in enumerate(known_totals, start=1):
                    cumulative += total / cohort_customers
                    if cumulative >= selected_cac:
                        payback = period
                        break
    else:
        if not isinstance(contribution, Decimal) or not isinstance(customer_contribution, Decimal):
            payback = "indeterminate"
        elif contribution <= 0 or customer_contribution <= 0:
            payback = "not_recoverable"
        elif not isinstance(selected_cac, Decimal):
            payback = "indeterminate"
        else:
            payback = selected_cac / customer_contribution

        if method == "fixed_horizon":
            expected_units = scalar_value(
                model["expected_units_per_customer_within_horizon"],
                "ltv_model.expected_units_per_customer_within_horizon",
            )
            horizon_value = scalar_value(model["horizon_periods"], "ltv_model.horizon_periods")
            horizon = int(horizon_value) if horizon_value is not None else "indeterminate"
            ltv = (
                contribution * expected_units
                if isinstance(contribution, Decimal) and expected_units is not None
                else "indeterminate"
            )
        else:
            churn = scalar_value(
                model["churn_rate_per_period"],
                "ltv_model.churn_rate_per_period",
                rate=True,
            )
            if churn is None or not isinstance(customer_contribution, Decimal):
                ltv = "indeterminate"
                expected_lifetime = "indeterminate"
            elif churn == 0:
                ltv = "zero_churn_requires_fixed_horizon_or_cohort"
                expected_lifetime = "zero_churn_requires_fixed_horizon_or_cohort"
            else:
                expected_lifetime = Decimal("1") / churn
                ltv = customer_contribution / churn

    if not isinstance(ltv, Decimal) or not isinstance(selected_cac, Decimal):
        ltv_to_cac: Decimal | str = "indeterminate"
    elif selected_cac == 0:
        ltv_to_cac = "not_meaningful_zero_cac"
    else:
        ltv_to_cac = ltv / selected_cac

    return {
        "contribution_per_period": customer_contribution,
        "payback_periods": payback,
        "ltv_method": method,
        "ltv": ltv,
        "ltv_horizon_periods": horizon,
        "expected_lifetime_periods": expected_lifetime,
        "ltv_to_cac": ltv_to_cac,
    }


def _acquisition_recovery_state(
    customer_economics: dict[str, object],
    selected_cac: Decimal | str,
    contribution: Decimal | str,
) -> bool | None:
    if not isinstance(contribution, Decimal):
        return None
    if contribution <= 0:
        return False
    if not isinstance(selected_cac, Decimal):
        return None
    payback = customer_economics["payback_periods"]
    if customer_economics["ltv_method"] == "observed_cohort":
        if isinstance(payback, (int, Decimal)):
            return True
        if payback == "not_observed_within_horizon":
            return False
        return None
    ltv = customer_economics["ltv"]
    return ltv >= selected_cac if isinstance(ltv, Decimal) else None


def _diagnose(
    scenario: dict[str, object],
    *,
    contribution: Decimal | str,
    capacity_status: str,
    selected_cac: Decimal | str,
    customer_economics: dict[str, object],
) -> list[str]:
    flags: list[str] = []
    if not isinstance(contribution, Decimal):
        return ["indeterminate"]
    if contribution <= 0:
        flags.append("negative_unit_economics")
    if capacity_status == "beyond_capacity":
        flags.append("break_even_beyond_capacity")

    recovered = _acquisition_recovery_state(customer_economics, selected_cac, contribution)
    if recovered is False:
        flags.append("acquisition_not_recovered")

    targets = scenario.get("targets", {})
    max_payback = (
        scalar_value(targets["max_payback_periods"], "targets.max_payback_periods")
        if "max_payback_periods" in targets
        else None
    )
    payback = customer_economics["payback_periods"]
    target_met: bool | None = None
    if max_payback is not None and isinstance(payback, (int, Decimal)):
        target_met = Decimal(payback) <= max_payback
        if recovered is True and not target_met:
            flags.append("unit_positive_but_cash_hungry")
    elif "max_payback_periods" not in targets:
        target_met = True

    acquisition = scenario["acquisition"]
    scope_ready = (
        acquisition["decision_cac_scope_complete"]
        and acquisition["selected_pool_matches_customer_cohort"]
    )
    scale_ready = (
        contribution > 0
        and capacity_status == "within_capacity"
        and scope_ready
        and recovered is True
        and target_met is True
    )
    if scale_ready:
        flags.append("profitable_to_scale")
    elif contribution > 0 and not any(
        flag in flags
        for flag in (
            "acquisition_not_recovered",
            "unit_positive_but_cash_hungry",
            "break_even_beyond_capacity",
        )
    ):
        flags.append("positive_unit_economics_unassessed_acquisition")
    return flags


def calculate_scenario(
    scenario: dict[str, object],
    *,
    mode: str,
    analysis_period: str,
    currency: str,
    unit_is_discrete: bool,
) -> dict[str, object]:
    drivers = scenario["drivers"]
    price = money_value(drivers["price_per_unit"], "drivers.price_per_unit", currency)
    cogs = money_value(drivers["cogs_per_unit"], "drivers.cogs_per_unit", currency)
    variable = money_value(
        drivers["other_variable_cost_per_unit"],
        "drivers.other_variable_cost_per_unit",
        currency,
    )
    volume = scalar_value(drivers["volume_units"], "drivers.volume_units")
    fixed = money_value(drivers["fixed_costs"], "drivers.fixed_costs", currency)
    capacity = (
        scalar_value(drivers["capacity_units"], "drivers.capacity_units")
        if "capacity_units" in drivers
        else None
    )

    gross_profit: Decimal | str = price - cogs if _known(price, cogs) else "indeterminate"
    contribution: Decimal | str = (
        price - cogs - variable if _known(price, cogs, variable) else "indeterminate"
    )
    if price is None or not isinstance(gross_profit, Decimal):
        gross_margin: Decimal | str = "indeterminate"
    elif price == 0:
        gross_margin = "indeterminate_zero_price"
    else:
        gross_margin = gross_profit / price
    if price is None or not isinstance(contribution, Decimal):
        contribution_margin: Decimal | str = "indeterminate"
    elif price == 0:
        contribution_margin = "indeterminate_zero_price"
    else:
        contribution_margin = contribution / price

    revenue: Decimal | str = price * volume if _known(price, volume) else "indeterminate"
    total_gross: Decimal | str = (
        gross_profit * volume
        if isinstance(gross_profit, Decimal) and volume is not None
        else "indeterminate"
    )
    total_contribution: Decimal | str = (
        contribution * volume
        if isinstance(contribution, Decimal) and volume is not None
        else "indeterminate"
    )
    after_fixed: Decimal | str = (
        total_contribution - fixed
        if isinstance(total_contribution, Decimal) and fixed is not None
        else "indeterminate"
    )

    if not isinstance(contribution, Decimal) or fixed is None:
        break_even_units: Decimal | str = "indeterminate"
        units_ceiling: int | str = "indeterminate"
        break_even_revenue: Decimal | str = "indeterminate"
        capacity_status = "unassessed"
    elif contribution <= 0:
        break_even_units = "no_finite_break_even"
        units_ceiling = "no_finite_break_even"
        break_even_revenue = "no_finite_break_even"
        capacity_status = "no_finite_break_even"
    else:
        break_even_units = fixed / contribution
        units_ceiling = (
            int(break_even_units.to_integral_value(rounding=ROUND_CEILING))
            if unit_is_discrete
            else "not_applicable_continuous_unit"
        )
        break_even_revenue = break_even_units * price if price is not None else "indeterminate"
        if "capacity_units" not in drivers or capacity is None:
            capacity_status = "unassessed"
        else:
            required = Decimal(units_ceiling) if unit_is_discrete else break_even_units
            capacity_status = "beyond_capacity" if required > capacity else "within_capacity"

    minimum_positive_price: Decimal | str = (
        cogs + variable if _known(cogs, variable) else "indeterminate"
    )
    maximum_variable_cost: Decimal | str = (
        max(Decimal("0"), price - cogs) if _known(price, cogs) else "indeterminate"
    )
    if not _known(cogs, variable, fixed, volume):
        minimum_break_even_price: Decimal | str = "indeterminate"
    elif volume == 0:
        minimum_break_even_price = "indeterminate_zero_volume"
    else:
        minimum_break_even_price = cogs + variable + fixed / volume

    cac, selected_cac = _calculate_cac(scenario, currency=currency)
    customer_economics = _calculate_customer_economics(
        scenario,
        contribution=contribution,
        selected_cac=selected_cac,
        currency=currency,
    )
    targets = scenario.get("targets", {})
    if "max_payback_periods" not in targets:
        maximum_cac: Decimal | str = "not_supplied"
    else:
        payback_target = scalar_value(
            targets["max_payback_periods"],
            "targets.max_payback_periods",
        )
        customer_contribution = customer_economics["contribution_per_period"]
        if not isinstance(customer_contribution, Decimal) or payback_target is None:
            maximum_cac = "indeterminate"
        elif customer_contribution <= 0:
            maximum_cac = "not_recoverable"
        else:
            maximum_cac = customer_contribution * payback_target

    if scenario["ltv_model"]["method"] != "constant_retention":
        maximum_churn: Decimal | str = "not_applicable"
        churn_constraint = "not_applicable"
    else:
        customer_contribution = customer_economics["contribution_per_period"]
        if not isinstance(customer_contribution, Decimal) or not isinstance(selected_cac, Decimal):
            maximum_churn = "indeterminate"
            churn_constraint = "indeterminate"
        elif selected_cac == 0:
            maximum_churn = "not_meaningful_zero_cac"
            churn_constraint = "not_meaningful_zero_cac"
        elif customer_contribution < 0:
            maximum_churn = "not_recoverable"
            churn_constraint = "not_recoverable"
        else:
            raw_churn = customer_contribution / selected_cac
            if raw_churn > 1:
                maximum_churn = Decimal("1")
                churn_constraint = "clamped_to_one"
            else:
                maximum_churn = raw_churn
                churn_constraint = "within_probability_range"

    diagnostic_flags = _diagnose(
        scenario,
        contribution=contribution,
        capacity_status=capacity_status,
        selected_cac=selected_cac,
        customer_economics=customer_economics,
    )

    missing_inputs, estimate_based = _input_quality(scenario)
    return {
        "name": scenario["name"],
        "mode": mode,
        "analysis_period": analysis_period,
        "estimate_based": estimate_based,
        "missing_inputs": missing_inputs,
        "unit_economics": {
            "price_per_unit": price,
            "gross_profit_per_unit": gross_profit,
            "gross_margin": gross_margin,
            "contribution_profit_per_unit": contribution,
            "contribution_margin": contribution_margin,
        },
        "period_economics": {
            "volume_units": volume,
            "revenue": revenue,
            "total_gross_profit": total_gross,
            "total_contribution_profit": total_contribution,
            "fixed_costs": fixed,
            "contribution_after_fixed_costs": after_fixed,
        },
        "break_even": {
            "units": break_even_units,
            "units_ceiling": units_ceiling,
            "revenue": break_even_revenue,
            "capacity_units": capacity,
            "capacity_status": capacity_status,
        },
        "breakpoints": {
            "minimum_price_for_positive_contribution": minimum_positive_price,
            "minimum_price_for_break_even_at_current_volume": minimum_break_even_price,
            "maximum_variable_cost_for_positive_contribution": maximum_variable_cost,
            "maximum_cac_for_payback_target": maximum_cac,
            "maximum_constant_churn_for_ltv_equal_cac": maximum_churn,
            "maximum_constant_churn_constraint": churn_constraint,
        },
        "cac": cac,
        "customer_economics": customer_economics,
        "diagnostic_flags": diagnostic_flags,
        "comparison_to_base": None,
    }


def _decision_metrics(result: dict[str, object]) -> dict[str, object]:
    return {
        "gross_profit_per_unit": result["unit_economics"]["gross_profit_per_unit"],
        "gross_margin": result["unit_economics"]["gross_margin"],
        "contribution_profit_per_unit": result["unit_economics"][
            "contribution_profit_per_unit"
        ],
        "contribution_margin": result["unit_economics"]["contribution_margin"],
        "revenue": result["period_economics"]["revenue"],
        "contribution_after_fixed_costs": result["period_economics"][
            "contribution_after_fixed_costs"
        ],
        "break_even_units": result["break_even"]["units"],
        "break_even_revenue": result["break_even"]["revenue"],
        "selected_cac": result["cac"]["selected_cac"],
        "customer_contribution_per_period": result["customer_economics"][
            "contribution_per_period"
        ],
        "payback_periods": result["customer_economics"]["payback_periods"],
        "ltv": result["customer_economics"]["ltv"],
        "ltv_to_cac": result["customer_economics"]["ltv_to_cac"],
    }


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def _compare_results(
    result: dict[str, object],
    source: dict[str, object],
) -> dict[str, object]:
    result_metrics = _decision_metrics(result)
    source_metrics = _decision_metrics(source)
    deltas = {
        key: result_metrics[key] - source_metrics[key]
        for key in result_metrics
        if _is_numeric(result_metrics[key]) and _is_numeric(source_metrics[key])
    }
    result_flags = set(result["diagnostic_flags"])
    source_flags = set(source["diagnostic_flags"])
    return {
        "deltas": deltas,
        "added_flags": sorted(result_flags - source_flags),
        "removed_flags": sorted(source_flags - result_flags),
    }


def calculate(payload: dict[str, object]) -> dict[str, object]:
    data = validate(payload)
    scenario_results = [
        calculate_scenario(
            scenario,
            mode=data["mode"],
            analysis_period=data["analysis_period"],
            currency=data["currency"],
            unit_is_discrete=data["unit_is_discrete"],
        )
        for scenario in data["scenarios"]
    ]
    results_by_name = {result["name"]: result for result in scenario_results}
    base_result = results_by_name["base"]
    for result in scenario_results:
        if result["name"] != "base":
            result["comparison_to_base"] = _compare_results(result, base_result)

    sensitivity_results: list[dict[str, object]] = []
    source_scenarios = {scenario["name"]: scenario for scenario in data["scenarios"]}
    for case in data.get("sensitivity_cases", []):
        source_name = case["source_scenario"]
        modified = _apply_overrides(source_scenarios[source_name], case["overrides"])
        modified["name"] = case["name"]
        case_result = calculate_scenario(
            modified,
            mode=data["mode"],
            analysis_period=data["analysis_period"],
            currency=data["currency"],
            unit_is_discrete=data["unit_is_discrete"],
        )
        source_result = results_by_name[source_name]
        comparison = _compare_results(case_result, source_result)
        case_result["source_scenario"] = source_name
        case_result["deltas"] = comparison["deltas"]
        case_result["added_flags"] = comparison["added_flags"]
        case_result["removed_flags"] = comparison["removed_flags"]
        if source_name != "base":
            case_result["comparison_to_base"] = _compare_results(case_result, base_result)
        sensitivity_results.append(case_result)
    return {
        "mode": data["mode"],
        "as_of_date": data["as_of_date"],
        "currency": data["currency"],
        "analysis_period": data["analysis_period"],
        "unit_name": data["unit_name"],
        "unit_is_discrete": data["unit_is_discrete"],
        "revenue_basis": data["revenue_basis"],
        "scenarios": scenario_results,
        "sensitivity_cases": sensitivity_results,
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
        payload = json.loads(raw, parse_float=Decimal)
        result = calculate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
