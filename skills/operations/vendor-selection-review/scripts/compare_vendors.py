#!/usr/bin/env python3
"""Compare vendor total cost while preserving non-cost selection constraints."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


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


def _score(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        raise ValueError(f"{path} must be an integer between 0 and 5")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return value


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    horizon = data.get("horizon_months")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("horizon_months must be a positive integer")
    hourly_cost = _money(data.get("internal_hourly_cost"), "internal_hourly_cost", currency)

    seen: set[str] = set()
    missing: list[str] = []
    results: list[dict[str, Any]] = []
    for index, raw_option in enumerate(_list(data.get("options"), "options")):
        path = f"options[{index}]"
        option = _object(raw_option, path)
        name = _string(option.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("option names must be unique")
        seen.add(name)
        initial = _money(option.get("initial_cost"), f"{path}.initial_cost", currency)
        monthly = _money(option.get("monthly_cost"), f"{path}.monthly_cost", currency)
        usage = _money(option.get("monthly_usage_cost"), f"{path}.monthly_usage_cost", currency)
        migration_hours = _scalar(option.get("migration_hours"), f"{path}.migration_hours")
        exit_cost = _money(option.get("exit_cost"), f"{path}.exit_cost", currency)
        contract = _integer(option.get("contract_months"), f"{path}.contract_months")
        lock_in = _score(option.get("lock_in_score"), f"{path}.lock_in_score")
        fit = _score(option.get("fit_score"), f"{path}.fit_score")
        reliability = _score(option.get("reliability_score"), f"{path}.reliability_score")
        values = {
            "initial_cost": initial,
            "monthly_cost": monthly,
            "monthly_usage_cost": usage,
            "migration_hours": migration_hours,
            "exit_cost": exit_cost,
        }
        for field, value in values.items():
            if value is None:
                missing.append(f"{path}.{field}")
        if hourly_cost is None:
            missing.append("internal_hourly_cost")
        complete = hourly_cost is not None and all(value is not None for value in values.values())
        migration_cost = tco = average = None
        if complete:
            assert initial is not None and monthly is not None and usage is not None and migration_hours is not None and exit_cost is not None and hourly_cost is not None
            migration_cost = migration_hours * hourly_cost
            tco = initial + migration_cost + (monthly + usage) * horizon + exit_cost
            average = tco / horizon
        flags: list[str] = []
        if lock_in >= 4:
            flags.append("high_lock_in")
        if contract >= horizon:
            flags.append("long_commitment")
        if fit <= 2:
            flags.append("low_fit")
        if reliability <= 2:
            flags.append("reliability_concern")
        results.append({
            "name": name,
            "status": "complete" if complete else "indeterminate",
            "migration_internal_cost": _number(migration_cost),
            "horizon_tco": _number(tco),
            "average_monthly_cost": _number(average),
            "fit_score": fit,
            "reliability_score": reliability,
            "lock_in_score": lock_in,
            "flags": flags,
        })

    comparable = [item for item in results if item["horizon_tco"] is not None]
    comparable.sort(key=lambda item: (item["horizon_tco"], item["name"]))
    return {
        "currency": currency,
        "horizon_months": horizon,
        "options": results,
        "cost_order": [item["name"] for item in comparable],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "quantified total cost only; fit, reliability, security, lock-in, and contract risk remain separate",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: compare_vendors.py <input.json>", file=sys.stderr)
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
