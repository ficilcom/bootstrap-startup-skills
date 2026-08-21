#!/usr/bin/env python3
"""Calculate cash runway scenarios from an anonymous JSON forecast."""

from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"quick", "detailed"}
GRANULARITIES = {"week", "month"}
DIRECTIONS = {"inflow", "outflow"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def add_months(value: date, months: int) -> date:
    """Return value shifted by calendar months, clamping the day if needed."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO date") from exc


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


def _money_value(value: object, path: str) -> Decimal | None:
    entry = _require_object(value, path)
    evidence = entry.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a known evidence state")
    amount = entry.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path} unknown amount must be null")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required when evidence is known")
    return _decimal(amount, f"{path}.amount")


def _validate_periods(
    periods: object,
    *,
    scenario_name: str,
    mode: str,
    as_of: date,
    currency: str,
) -> None:
    if not isinstance(periods, list) or not periods:
        raise ValueError(f"scenario {scenario_name} periods must be a nonempty list")

    period_ids: set[str] = set()
    movement_ids: set[str] = set()
    previous_end: date | None = None
    parsed_periods: list[tuple[date, date, str]] = []

    for index, raw_period in enumerate(periods):
        path = f"scenario {scenario_name} period {index}"
        period = _require_object(raw_period, path)
        period_id = _require_nonempty_string(period.get("id"), f"{path}.id")
        if period_id in period_ids:
            raise ValueError(f"duplicate period id {period_id} in scenario {scenario_name}")
        period_ids.add(period_id)

        start = _parse_date(period.get("start_date"), f"{path}.start_date")
        end = _parse_date(period.get("end_date"), f"{path}.end_date")
        if start > end:
            raise ValueError(f"{path} start_date must not follow end_date")
        if index == 0 and start != as_of:
            raise ValueError(f"scenario {scenario_name} first period must start on as_of_date")
        if previous_end is not None and start != previous_end + timedelta(days=1):
            raise ValueError(f"scenario {scenario_name} periods must be consecutive")
        previous_end = end

        granularity = period.get("granularity")
        if granularity not in GRANULARITIES:
            raise ValueError(f"{path}.granularity must be week or month")
        parsed_periods.append((start, end, granularity))

        movements = period.get("movements")
        if not isinstance(movements, list):
            raise ValueError(f"{path}.movements must be a list")
        for movement_index, raw_movement in enumerate(movements):
            movement_path = f"{path} movement {movement_index}"
            movement = _require_object(raw_movement, movement_path)
            movement_id = _require_nonempty_string(movement.get("id"), f"{movement_path}.id")
            if movement_id in movement_ids:
                raise ValueError(f"duplicate movement id {movement_id} in scenario {scenario_name}")
            movement_ids.add(movement_id)
            _require_nonempty_string(movement.get("label"), f"{movement_path}.label")
            if movement.get("direction") not in DIRECTIONS:
                raise ValueError(f"{movement_path}.direction must be inflow or outflow")
            movement_currency = movement.get("currency", currency)
            if movement_currency != currency:
                raise ValueError(f"{movement_path}.currency must match top-level currency")
            _money_value(movement.get("amount"), f"{movement_path}.amount")

    horizon_end = add_months(as_of, 12) - timedelta(days=1)
    if parsed_periods[-1][1] != horizon_end:
        raise ValueError(f"scenario {scenario_name} must end at the 12-month horizon")

    if mode == "detailed":
        if len(parsed_periods) < 13 or any(item[2] != "week" for item in parsed_periods[:13]):
            raise ValueError(f"scenario {scenario_name} first 13 periods must be weekly")
        if any(item[2] != "month" for item in parsed_periods[13:]):
            raise ValueError(f"scenario {scenario_name} periods after week 13 must be monthly")
        for start, end, _ in parsed_periods[:13]:
            if (end - start).days != 6:
                raise ValueError(f"scenario {scenario_name} weekly periods must contain seven days")
    elif any(item[2] != "month" for item in parsed_periods):
        raise ValueError(f"scenario {scenario_name} quick-mode periods must be monthly")


def _validate_warning_policy(value: object) -> None:
    if value is None:
        return
    policy = _require_object(value, "warning_policy")
    expected = {"critical_days", "warning_days", "watch_days"}
    if set(policy) != expected:
        raise ValueError("warning_policy must contain critical_days, warning_days, and watch_days")
    numbers: list[int] = []
    for field in ("critical_days", "warning_days", "watch_days"):
        raw = policy[field]
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            raise ValueError(f"warning_policy.{field} must be a positive integer")
        numbers.append(raw)
    if numbers != sorted(numbers) or len(set(numbers)) != 3:
        raise ValueError("warning_policy day thresholds must be strictly ascending")


def validate(payload: object) -> dict[str, Any]:
    """Validate payload structure and return it unchanged."""
    data = _require_object(payload, "payload")
    mode = data.get("mode")
    if mode not in MODES:
        raise ValueError("mode must be quick or detailed")
    as_of = _parse_date(data.get("as_of_date"), "as_of_date")
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter code")

    gross_cash = _money_value(data.get("gross_cash"), "gross_cash")
    restricted_cash = _money_value(data.get("restricted_cash"), "restricted_cash")
    _money_value(data.get("minimum_cash_buffer"), "minimum_cash_buffer")
    if gross_cash is not None and restricted_cash is not None and restricted_cash > gross_cash:
        raise ValueError("restricted_cash cannot exceed gross_cash")

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must be a nonempty list")
    scenario_names: set[str] = set()
    for index, raw_scenario in enumerate(scenarios):
        scenario = _require_object(raw_scenario, f"scenario {index}")
        name = _require_nonempty_string(scenario.get("name"), f"scenario {index}.name")
        if name in scenario_names:
            raise ValueError(f"duplicate scenario name {name}")
        scenario_names.add(name)
        _validate_periods(
            scenario.get("periods"),
            scenario_name=name,
            mode=mode,
            as_of=as_of,
            currency=currency,
        )
    if "base" not in scenario_names:
        raise ValueError("scenarios must include a base scenario")

    _validate_warning_policy(data.get("warning_policy"))
    actions = data.get("modeled_actions", [])
    if not isinstance(actions, list):
        raise ValueError("modeled_actions must be a list")
    return data


def _runway_months(as_of: date, crossing: date | None) -> Decimal | str:
    if crossing is None:
        return "more_than_12_months"
    return Decimal((crossing - as_of).days) / Decimal("30.4375")


def _warning_status(as_of: date, crossing: date | None, policy: dict[str, object] | None) -> str:
    if crossing is None:
        return "stable"
    thresholds = policy or {
        "critical_days": 91,
        "warning_days": 183,
        "watch_days": 366,
    }
    elapsed = (crossing - as_of).days
    if elapsed < thresholds["critical_days"]:
        return "critical"
    if elapsed < thresholds["warning_days"]:
        return "warning"
    return "watch"


def _scenario_missing_inputs(
    scenario: dict[str, Any], core_missing: list[str]
) -> list[str]:
    missing = list(core_missing)
    for period in scenario["periods"]:
        for movement in period["movements"]:
            if movement["amount"]["evidence"] == "unknown":
                missing.append(f"movement:{movement['id']}")
    return missing


def _indeterminate_scenario(name: str, missing_inputs: list[str]) -> dict[str, object]:
    return {
        "name": name,
        "warning_status": "indeterminate",
        "missing_inputs": missing_inputs,
        "periods": [],
        "buffer_crossing_period": None,
        "buffer_crossing_date": None,
        "buffer_runway": None,
        "zero_crossing_period": None,
        "zero_crossing_date": None,
        "zero_cash_runway": None,
        "lowest_closing_available_cash": None,
        "lowest_cash_period": None,
        "maximum_funding_gap": None,
        "last_modeled_period": None,
        "comparison_to_base": None,
    }


def calculate_scenario(
    scenario: dict[str, Any],
    *,
    opening_available_cash: Decimal,
    minimum_cash_buffer: Decimal,
    as_of: date,
    warning_policy: dict[str, object] | None,
) -> dict[str, object]:
    """Calculate one fully known scenario."""
    opening = opening_available_cash
    lowest: Decimal | None = None
    lowest_period: str | None = None
    buffer_crossing_period: str | None = None
    buffer_crossing_date: date | None = None
    zero_crossing_period: str | None = None
    zero_crossing_date: date | None = None
    calculated_periods: list[dict[str, object]] = []

    for period in scenario["periods"]:
        inflows = Decimal("0")
        outflows = Decimal("0")
        for movement in period["movements"]:
            amount = _money_value(movement["amount"], f"movement {movement['id']}.amount")
            if amount is None:
                raise ValueError("calculate_scenario received an unknown movement")
            if movement["direction"] == "inflow":
                inflows += amount
            else:
                outflows += amount

        closing = opening + inflows - outflows
        period_end = date.fromisoformat(period["end_date"])
        if lowest is None or closing < lowest:
            lowest = closing
            lowest_period = period["id"]
        if buffer_crossing_date is None and closing < minimum_cash_buffer:
            buffer_crossing_period = period["id"]
            buffer_crossing_date = period_end
        if zero_crossing_date is None and closing < 0:
            zero_crossing_period = period["id"]
            zero_crossing_date = period_end

        calculated_periods.append(
            {
                "id": period["id"],
                "start_date": period["start_date"],
                "end_date": period["end_date"],
                "granularity": period["granularity"],
                "opening_available_cash": opening,
                "cash_inflows": inflows,
                "cash_outflows": outflows,
                "net_cash_flow": inflows - outflows,
                "closing_available_cash": closing,
            }
        )
        opening = closing

    assert lowest is not None
    earliest_crossing = min(
        (item for item in (buffer_crossing_date, zero_crossing_date) if item is not None),
        default=None,
    )
    return {
        "name": scenario["name"],
        "warning_status": _warning_status(as_of, earliest_crossing, warning_policy),
        "missing_inputs": [],
        "periods": calculated_periods,
        "buffer_crossing_period": buffer_crossing_period,
        "buffer_crossing_date": buffer_crossing_date.isoformat() if buffer_crossing_date else None,
        "buffer_runway": _runway_months(as_of, buffer_crossing_date),
        "zero_crossing_period": zero_crossing_period,
        "zero_crossing_date": zero_crossing_date.isoformat() if zero_crossing_date else None,
        "zero_cash_runway": _runway_months(as_of, zero_crossing_date),
        "lowest_closing_available_cash": lowest,
        "lowest_cash_period": lowest_period,
        "maximum_funding_gap": max(Decimal("0"), minimum_cash_buffer - lowest),
        "last_modeled_period": calculated_periods[-1]["id"],
        "comparison_to_base": None,
    }


def _crossing_days(result: dict[str, object], field: str, as_of: date) -> int | None:
    value = result[field]
    if value is None:
        return None
    return (date.fromisoformat(value) - as_of).days


def _comparison(
    result: dict[str, object], base: dict[str, object], as_of: date
) -> dict[str, object] | None:
    if result["warning_status"] == "indeterminate" or base["warning_status"] == "indeterminate":
        return None

    def crossing_delta(field: str) -> int | None:
        result_days = _crossing_days(result, field, as_of)
        base_days = _crossing_days(base, field, as_of)
        if result_days is None or base_days is None:
            return None
        return result_days - base_days

    return {
        "lowest_cash_delta": result["lowest_closing_available_cash"]
        - base["lowest_closing_available_cash"],
        "maximum_funding_gap_delta": result["maximum_funding_gap"]
        - base["maximum_funding_gap"],
        "buffer_crossing_days_delta": crossing_delta("buffer_crossing_date"),
        "zero_crossing_days_delta": crossing_delta("zero_crossing_date"),
    }


def calculate(payload: dict[str, object]) -> dict[str, object]:
    """Validate a runway payload and return calculated results."""
    data = validate(payload)
    as_of = date.fromisoformat(data["as_of_date"])
    gross_cash = _money_value(data["gross_cash"], "gross_cash")
    restricted_cash = _money_value(data["restricted_cash"], "restricted_cash")
    minimum_cash_buffer = _money_value(data["minimum_cash_buffer"], "minimum_cash_buffer")
    core_values = {
        "gross_cash": gross_cash,
        "restricted_cash": restricted_cash,
        "minimum_cash_buffer": minimum_cash_buffer,
    }
    core_missing = [name for name, value in core_values.items() if value is None]
    opening_available_cash = (
        gross_cash - restricted_cash
        if gross_cash is not None and restricted_cash is not None
        else None
    )

    scenario_results: list[dict[str, object]] = []
    for scenario in data["scenarios"]:
        missing_inputs = _scenario_missing_inputs(scenario, core_missing)
        if missing_inputs:
            result = _indeterminate_scenario(scenario["name"], missing_inputs)
        else:
            assert opening_available_cash is not None
            assert minimum_cash_buffer is not None
            result = calculate_scenario(
                scenario,
                opening_available_cash=opening_available_cash,
                minimum_cash_buffer=minimum_cash_buffer,
                as_of=as_of,
                warning_policy=data.get("warning_policy"),
            )
        scenario_results.append(result)

    base = next(result for result in scenario_results if result["name"] == "base")
    for result in scenario_results:
        if result is not base:
            result["comparison_to_base"] = _comparison(result, base, as_of)

    provisional = data["mode"] == "quick" or any(
        result["warning_status"] == "indeterminate" for result in scenario_results
    )
    return {
        "mode": data["mode"],
        "as_of_date": data["as_of_date"],
        "currency": data["currency"],
        "opening_available_cash": opening_available_cash,
        "minimum_cash_buffer": minimum_cash_buffer,
        "provisional": provisional,
        "missing_core_inputs": core_missing,
        "warning_status": base["warning_status"],
        "scenarios": scenario_results,
        "modeled_actions": [],
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
