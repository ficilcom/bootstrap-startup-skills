#!/usr/bin/env python3
"""Calculate fully loaded first-hire affordability from an anonymous JSON model."""

from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import sys
from datetime import date
from decimal import Decimal
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
REQUIRED_SCENARIOS = {"base", "downside", "delayed"}
REQUIRED_COSTS = {
    "annual_salary",
    "employer_contributions_rate",
    "benefits_monthly",
    "recruiting_one_time",
    "equipment_software_one_time",
    "equipment_software_monthly",
    "onboarding_one_time",
    "management_time_monthly",
    "separation_contingency_one_time",
    "productivity_ramp_costs",
    "benefit_ramp_monthly",
}


def add_months(value: date, months: int) -> date:
    """Shift a date by calendar months, clamping its day where needed."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _nonnegative(value: object, path: str) -> Decimal:
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


def money(value: object, path: str, currency: str) -> Decimal | None:
    """Validate a money object and return its known amount, if any."""
    entry = _object(value, path)
    if set(entry) - {"amount", "evidence", "currency"}:
        raise ValueError(f"{path} contains unsupported fields")
    if entry.get("evidence") not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    if entry.get("currency", currency) != currency:
        raise ValueError(f"{path}.currency must match top-level currency")
    amount = entry.get("amount")
    if entry["evidence"] == "unknown":
        if amount is not None:
            raise ValueError(f"{path} unknown amount must be null")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required when evidence is known")
    return _nonnegative(amount, f"{path}.amount")


def rate(value: object, path: str) -> Decimal | None:
    """Validate a rate object and return its known value, if any."""
    entry = _object(value, path)
    if set(entry) != {"value", "evidence"}:
        raise ValueError(f"{path} must contain value and evidence")
    if entry.get("evidence") not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    raw = entry.get("value")
    if entry["evidence"] == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown value must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.value is required when evidence is known")
    result = _nonnegative(raw, f"{path}.value")
    if result > 1:
        raise ValueError(f"{path}.value must be from 0 through 1")
    return result


def _month_index(value: object, path: str, horizon: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < horizon:
        raise ValueError(f"{path} must be an integer from 0 through planning_horizon_months - 1")
    return value


def _validate_cash_pair(value: object, path: str, currency: str) -> None:
    entry = _object(value, path)
    if set(entry) != {"inflows", "outflows"}:
        raise ValueError(f"{path} must contain inflows and outflows")
    money(entry["inflows"], f"{path}.inflows", currency)
    money(entry["outflows"], f"{path}.outflows", currency)


def _validate_costs(value: object, path: str, currency: str) -> None:
    costs = _object(value, path)
    if set(costs) != REQUIRED_COSTS:
        missing = REQUIRED_COSTS - set(costs)
        extra = set(costs) - REQUIRED_COSTS
        pieces = []
        if missing:
            pieces.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            pieces.append(f"unsupported {', '.join(sorted(extra))}")
        raise ValueError(f"{path} fields are invalid: {'; '.join(pieces)}")
    for field in REQUIRED_COSTS - {
        "employer_contributions_rate",
        "productivity_ramp_costs",
        "benefit_ramp_monthly",
    }:
        money(costs[field], f"{path}.{field}", currency)
    rate(costs["employer_contributions_rate"], f"{path}.employer_contributions_rate")
    for field, must_be_nonempty in (
        ("productivity_ramp_costs", False),
        ("benefit_ramp_monthly", True),
    ):
        entries = costs[field]
        if not isinstance(entries, list) or (must_be_nonempty and not entries):
            qualifier = "a nonempty list" if must_be_nonempty else "a list"
            raise ValueError(f"{path}.{field} must be {qualifier}")
        for index, entry in enumerate(entries):
            money(entry, f"{path}.{field}[{index}]", currency)


def validate(payload: object) -> dict[str, Any]:
    """Validate the input contract and return it unchanged."""
    data = _object(payload, "payload")
    required = {
        "as_of_date",
        "currency",
        "opening_available_cash",
        "minimum_cash_buffer",
        "planning_horizon_months",
        "scenarios",
    }
    if set(data) != required:
        raise ValueError("payload must contain only the documented top-level fields")
    try:
        date.fromisoformat(_string(data.get("as_of_date"), "as_of_date"))
    except ValueError as exc:
        raise ValueError("as_of_date must be an ISO date") from exc
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter code")
    horizon = data.get("planning_horizon_months")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 60:
        raise ValueError("planning_horizon_months must be an integer from 1 through 60")
    money(data.get("opening_available_cash"), "opening_available_cash", currency)
    money(data.get("minimum_cash_buffer"), "minimum_cash_buffer", currency)

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        raise ValueError("scenarios must contain exactly base, downside, and delayed")
    names: set[str] = set()
    for index, raw_scenario in enumerate(scenarios):
        path = f"scenario {index}"
        scenario = _object(raw_scenario, path)
        expected = {"name", "hire_start_month", "pre_hire_monthly_cash", "pre_hire_adjustments", "hiring_costs"}
        if set(scenario) != expected:
            raise ValueError(f"{path} must contain only the documented scenario fields")
        name = _string(scenario.get("name"), f"{path}.name")
        if name in names:
            raise ValueError(f"duplicate scenario name {name}")
        names.add(name)
        start = _month_index(scenario.get("hire_start_month"), f"{path}.hire_start_month", horizon)
        _validate_cash_pair(scenario.get("pre_hire_monthly_cash"), f"{path}.pre_hire_monthly_cash", currency)
        adjustments = scenario.get("pre_hire_adjustments")
        if not isinstance(adjustments, list):
            raise ValueError(f"{path}.pre_hire_adjustments must be a list")
        seen_months: set[int] = set()
        for adjustment_index, raw_adjustment in enumerate(adjustments):
            adjustment_path = f"{path}.pre_hire_adjustments[{adjustment_index}]"
            adjustment = _object(raw_adjustment, adjustment_path)
            if set(adjustment) != {"month_index", "inflows", "outflows"}:
                raise ValueError(f"{adjustment_path} must contain month_index, inflows, and outflows")
            month = _month_index(adjustment.get("month_index"), f"{adjustment_path}.month_index", horizon)
            if month in seen_months:
                raise ValueError(f"{path}.pre_hire_adjustments must not repeat month_index")
            seen_months.add(month)
            money(adjustment["inflows"], f"{adjustment_path}.inflows", currency)
            money(adjustment["outflows"], f"{adjustment_path}.outflows", currency)
        _validate_costs(scenario.get("hiring_costs"), f"{path}.hiring_costs", currency)
        if name == "delayed" and start == 0:
            raise ValueError("delayed.hire_start_month must be greater than zero")
    if names != REQUIRED_SCENARIOS:
        raise ValueError("scenarios must contain exactly base, downside, and delayed")
    return data


def _input_quality(value: object, path: str = "") -> tuple[list[str], bool]:
    missing: list[str] = []
    estimated = False
    if isinstance(value, dict):
        if value.get("evidence") in EVIDENCE_STATES:
            estimated = value["evidence"] == "estimated"
            raw = value.get("amount", value.get("value"))
            if value["evidence"] == "unknown" and raw is None:
                missing.append(path)
        else:
            for key, child in value.items():
                child_missing, child_estimated = _input_quality(child, f"{path}.{key}" if path else key)
                missing.extend(child_missing)
                estimated = estimated or child_estimated
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_missing, child_estimated = _input_quality(child, f"{path}[{index}]")
            missing.extend(child_missing)
            estimated = estimated or child_estimated
    return missing, estimated


def _amount(value: object, path: str, currency: str) -> Decimal:
    result = money(value, path, currency)
    if result is None:
        raise ValueError(f"{path} is unknown")
    return result


def _rate_value(value: object, path: str) -> Decimal:
    result = rate(value, path)
    if result is None:
        raise ValueError(f"{path} is unknown")
    return result


def _date_label(as_of: date, month_index: int) -> tuple[str, str]:
    start = add_months(as_of, month_index)
    end = add_months(as_of, month_index + 1)
    return start.isoformat(), (end.fromordinal(end.toordinal() - 1)).isoformat()


def _cost_profile(costs: dict[str, Any], currency: str) -> dict[str, Any]:
    salary = _amount(costs["annual_salary"], "hiring_costs.annual_salary", currency) / Decimal(12)
    employer = salary * _rate_value(costs["employer_contributions_rate"], "hiring_costs.employer_contributions_rate")
    recurring = {
        "salary_monthly": salary,
        "employer_contributions_monthly": employer,
        "benefits_monthly": _amount(costs["benefits_monthly"], "hiring_costs.benefits_monthly", currency),
        "equipment_software_monthly": _amount(costs["equipment_software_monthly"], "hiring_costs.equipment_software_monthly", currency),
        "management_time_monthly": _amount(costs["management_time_monthly"], "hiring_costs.management_time_monthly", currency),
    }
    one_time = {
        "recruiting_one_time": _amount(costs["recruiting_one_time"], "hiring_costs.recruiting_one_time", currency),
        "equipment_software_one_time": _amount(costs["equipment_software_one_time"], "hiring_costs.equipment_software_one_time", currency),
        "onboarding_one_time": _amount(costs["onboarding_one_time"], "hiring_costs.onboarding_one_time", currency),
        "separation_contingency_one_time": _amount(costs["separation_contingency_one_time"], "hiring_costs.separation_contingency_one_time", currency),
    }
    productivity = [_amount(item, "hiring_costs.productivity_ramp_costs", currency) for item in costs["productivity_ramp_costs"]]
    benefits = [_amount(item, "hiring_costs.benefit_ramp_monthly", currency) for item in costs["benefit_ramp_monthly"]]
    return {"recurring": recurring, "one_time": one_time, "productivity": productivity, "benefits": benefits}


def _calculate_known_scenario(
    scenario: dict[str, Any],
    *,
    as_of: date,
    currency: str,
    opening_cash: Decimal,
    minimum_buffer: Decimal,
    horizon: int,
    hire_start_month: int,
    include_periods: bool = True,
) -> dict[str, Any]:
    profile = _cost_profile(scenario["hiring_costs"], currency)
    ordinary = scenario["pre_hire_monthly_cash"]
    monthly_inflows = _amount(ordinary["inflows"], "pre_hire_monthly_cash.inflows", currency)
    monthly_outflows = _amount(ordinary["outflows"], "pre_hire_monthly_cash.outflows", currency)
    adjustments = {entry["month_index"]: entry for entry in scenario["pre_hire_adjustments"]}
    cash = opening_cash
    lowest_cash = opening_cash
    lowest_month: int | None = None
    buffer_breach_month: int | None = None
    cash_shortfall_month: int | None = None
    cumulative_cost = Decimal("0")
    cumulative_benefit = Decimal("0")
    benefit_payback_month: int | None = None
    component_totals: dict[str, Decimal] = {key: Decimal("0") for key in (*profile["recurring"], *profile["one_time"], "productivity_ramp_costs")}
    periods: list[dict[str, Any]] = []

    for month in range(horizon):
        adjustment = adjustments.get(month)
        adjustment_inflows = _amount(adjustment["inflows"], "pre_hire_adjustment.inflows", currency) if adjustment else Decimal("0")
        adjustment_outflows = _amount(adjustment["outflows"], "pre_hire_adjustment.outflows", currency) if adjustment else Decimal("0")
        pre_hire_closing = cash + monthly_inflows - monthly_outflows + adjustment_inflows - adjustment_outflows
        hire_cost = Decimal("0")
        hire_benefit = Decimal("0")
        breakdown: dict[str, Decimal] = {}
        if month >= hire_start_month:
            months_since_hire = month - hire_start_month
            for key, amount in profile["recurring"].items():
                breakdown[key] = amount
                component_totals[key] += amount
                hire_cost += amount
            if months_since_hire == 0:
                for key, amount in profile["one_time"].items():
                    breakdown[key] = amount
                    component_totals[key] += amount
                    hire_cost += amount
            productivity = profile["productivity"]
            if months_since_hire < len(productivity):
                amount = productivity[months_since_hire]
                breakdown["productivity_ramp_costs"] = amount
                component_totals["productivity_ramp_costs"] += amount
                hire_cost += amount
            benefits = profile["benefits"]
            hire_benefit = benefits[min(months_since_hire, len(benefits) - 1)]
            cumulative_cost += hire_cost
            cumulative_benefit += hire_benefit
            if benefit_payback_month is None and cumulative_benefit >= cumulative_cost:
                benefit_payback_month = month
        closing = pre_hire_closing - hire_cost + hire_benefit
        if closing < lowest_cash:
            lowest_cash, lowest_month = closing, month
        if buffer_breach_month is None and closing < minimum_buffer:
            buffer_breach_month = month
        if cash_shortfall_month is None and closing < 0:
            cash_shortfall_month = month
        if include_periods:
            start_date, end_date = _date_label(as_of, month)
            periods.append({
                "month_index": month,
                "start_date": start_date,
                "end_date": end_date,
                "opening_cash": cash,
                "pre_hire_inflows": monthly_inflows + adjustment_inflows,
                "pre_hire_outflows": monthly_outflows + adjustment_outflows,
                "pre_hire_closing_cash": pre_hire_closing,
                "hire_cost": hire_cost,
                "hire_benefit_cash": hire_benefit,
                "net_hire_cash_effect": hire_benefit - hire_cost,
                "closing_cash": closing,
                "cash_above_buffer": closing - minimum_buffer,
                "hire_cost_breakdown": breakdown,
            })
        cash = closing
    status = "maintains_buffer" if buffer_breach_month is None else ("cash_shortfall" if cash_shortfall_month is not None else "buffer_breach")
    return {
        "status": status,
        "hire_start_month": hire_start_month,
        "periods": periods,
        "lowest_closing_cash": lowest_cash,
        "lowest_cash_month": lowest_month,
        "buffer_breach_month": buffer_breach_month,
        "cash_shortfall_month": cash_shortfall_month,
        "buffer_runway_months": "more_than_horizon" if buffer_breach_month is None else Decimal(buffer_breach_month + 1),
        "zero_cash_runway_months": "more_than_horizon" if cash_shortfall_month is None else Decimal(cash_shortfall_month + 1),
        "maximum_buffer_funding_gap": max(Decimal("0"), minimum_buffer - lowest_cash),
        "total_hire_cost": cumulative_cost,
        "total_hire_benefit_cash": cumulative_benefit,
        "net_hire_cash_effect": cumulative_benefit - cumulative_cost,
        "benefit_payback_month": benefit_payback_month,
        "cost_component_totals": component_totals,
    }


def _indeterminate(name: str, missing: list[str], start: int) -> dict[str, Any]:
    return {
        "name": name,
        "status": "indeterminate",
        "hire_start_month": start,
        "missing_inputs": missing,
        "periods": [],
        "lowest_closing_cash": None,
        "lowest_cash_month": None,
        "buffer_breach_month": None,
        "cash_shortfall_month": None,
        "buffer_runway_months": None,
        "zero_cash_runway_months": None,
        "maximum_buffer_funding_gap": None,
        "total_hire_cost": None,
        "total_hire_benefit_cash": None,
        "net_hire_cash_effect": None,
        "benefit_payback_month": None,
        "cost_component_totals": None,
    }


def _first_robust_start(
    scenarios: dict[str, dict[str, Any]], *, as_of: date, currency: str, opening: Decimal, buffer: Decimal, horizon: int
) -> int | None:
    for start in range(horizon):
        base = _calculate_known_scenario(scenarios["base"], as_of=as_of, currency=currency, opening_cash=opening, minimum_buffer=buffer, horizon=horizon, hire_start_month=start, include_periods=False)
        downside = _calculate_known_scenario(scenarios["downside"], as_of=as_of, currency=currency, opening_cash=opening, minimum_buffer=buffer, horizon=horizon, hire_start_month=start, include_periods=False)
        if base["status"] == downside["status"] == "maintains_buffer":
            return start
    return None


def calculate(payload: object) -> dict[str, Any]:
    """Return affordability results without performing external actions."""
    data = validate(payload)
    as_of = date.fromisoformat(data["as_of_date"])
    currency = data["currency"]
    horizon = data["planning_horizon_months"]
    opening = money(data["opening_available_cash"], "opening_available_cash", currency)
    buffer = money(data["minimum_cash_buffer"], "minimum_cash_buffer", currency)
    scenario_map = {scenario["name"]: scenario for scenario in data["scenarios"]}
    top_missing, top_estimated = _input_quality({key: data[key] for key in ("opening_available_cash", "minimum_cash_buffer")})
    results: list[dict[str, Any]] = []
    scenario_missing: dict[str, list[str]] = {}
    estimated = top_estimated
    for name in ("base", "downside", "delayed"):
        scenario = scenario_map[name]
        missing, scenario_estimated = _input_quality(scenario, f"scenarios.{name}")
        missing = top_missing + missing
        scenario_missing[name] = missing
        estimated = estimated or scenario_estimated
        if missing:
            results.append(_indeterminate(name, missing, scenario["hire_start_month"]))
        else:
            result = _calculate_known_scenario(scenario, as_of=as_of, currency=currency, opening_cash=opening, minimum_buffer=buffer, horizon=horizon, hire_start_month=scenario["hire_start_month"])
            result["name"] = name
            result["missing_inputs"] = []
            results.append(result)

    result_by_name = {result["name"]: result for result in results}
    if any(scenario_missing.values()):
        recommendation = {
            "outcome": "indeterminate",
            "earliest_affordable_hire_start_month": None,
            "execution_conditions": ["Confirm every unknown cash, operating-cash, and employment-cost input before deciding."],
        }
    else:
        robust_start = _first_robust_start(scenario_map, as_of=as_of, currency=currency, opening=opening, buffer=buffer, horizon=horizon)
        base_now = _calculate_known_scenario(scenario_map["base"], as_of=as_of, currency=currency, opening_cash=opening, minimum_buffer=buffer, horizon=horizon, hire_start_month=0, include_periods=False)
        downside_now = _calculate_known_scenario(scenario_map["downside"], as_of=as_of, currency=currency, opening_cash=opening, minimum_buffer=buffer, horizon=horizon, hire_start_month=0, include_periods=False)
        if base_now["status"] == downside_now["status"] == "maintains_buffer":
            outcome, conditions = "hire_now", ["Reconfirm material estimated employment costs and downside assumptions immediately before external hiring actions."]
        elif base_now["status"] == "maintains_buffer":
            outcome, conditions = "conditional", [f"Improve or confirm downside cash by at least {downside_now['maximum_buffer_funding_gap']} {currency} before committing to a start date.", "Recalculate after any change to hiring cost, cash collections, or benefit timing."]
        elif robust_start is not None:
            outcome, conditions = "defer", [f"Do not start before month {robust_start}; revalidate base and downside cash at that time.", "Set a withdrawal trigger if the refreshed forecast falls below the minimum cash buffer."]
        else:
            outcome, conditions = "unaffordable", ["Do not commit to the hire under the modeled horizon without a separately verified improvement in cash, costs, or timing.", "Define a withdrawal trigger at the first projected minimum-cash-buffer breach."]
        recommendation = {
            "outcome": outcome,
            "earliest_affordable_hire_start_month": robust_start,
            "execution_conditions": conditions,
            "current_start_comparison": {"base": base_now["status"], "downside": downside_now["status"]},
        }
    return {
        "as_of_date": data["as_of_date"],
        "currency": currency,
        "planning_horizon_months": horizon,
        "opening_available_cash": opening,
        "minimum_cash_buffer": buffer,
        "provisional": estimated or any(scenario_missing.values()),
        "scenarios": results,
        "recommendation": recommendation,
    }


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input path, or - for standard input")
    args = parser.parse_args(argv)
    try:
        with sys.stdin if args.input == "-" else open(args.input, encoding="utf-8") as stream:
            payload = json.load(stream)
        print(json.dumps(calculate(payload), ensure_ascii=False, indent=2, default=_json_default))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
