#!/usr/bin/env python3
"""Calculate unit economics scenarios from an anonymous JSON model."""

from __future__ import annotations

import argparse
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
    if "base" not in names:
        raise ValueError("scenarios must include base")

    sensitivity_cases = data.get("sensitivity_cases", [])
    if not isinstance(sensitivity_cases, list):
        raise ValueError("sensitivity_cases must be a list")
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
        },
        "cac": {},
        "customer_economics": {},
        "diagnostic_flags": [],
        "comparison_to_base": None,
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
    return {
        "mode": data["mode"],
        "as_of_date": data["as_of_date"],
        "currency": data["currency"],
        "analysis_period": data["analysis_period"],
        "unit_name": data["unit_name"],
        "unit_is_discrete": data["unit_is_discrete"],
        "revenue_basis": data["revenue_basis"],
        "scenarios": scenario_results,
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
        payload = json.loads(raw, parse_float=Decimal)
        result = calculate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
