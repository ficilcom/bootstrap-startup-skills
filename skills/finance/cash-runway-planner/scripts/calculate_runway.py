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


def calculate(payload: dict[str, object]) -> dict[str, object]:
    """Validate a runway payload and return calculated results."""
    data = validate(payload)
    return {"mode": data["mode"], "currency": data["currency"]}


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
