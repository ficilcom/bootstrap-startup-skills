#!/usr/bin/env python3
"""Measure forecast error and calculate an evidence-bounded pipeline range."""

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


def _rate(value: Decimal | None, path: str) -> Decimal | None:
    if value is not None and value > 1:
        raise ValueError(f"{path} must be between 0 and 1")
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
    period = _string(data.get("forecast_period"), "forecast_period")
    target = _money(data.get("target"), "target", currency)
    minimum_sample = data.get("minimum_stage_sample")
    if isinstance(minimum_sample, bool) or not isinstance(minimum_sample, int) or minimum_sample <= 0:
        raise ValueError("minimum_stage_sample must be a positive integer")

    history_flags: list[str] = []
    total_actual = Decimal(0)
    total_forecast = Decimal(0)
    absolute_error = Decimal(0)
    history_complete = True
    for index, raw_period in enumerate(_list(data.get("history"), "history")):
        path = f"history[{index}]"
        item = _object(raw_period, path)
        _string(item.get("period"), f"{path}.period")
        forecast = _money(item.get("forecast"), f"{path}.forecast", currency)
        actual = _money(item.get("actual"), f"{path}.actual", currency)
        if forecast is None or actual is None:
            history_complete = False
            continue
        total_forecast += forecast
        total_actual += actual
        absolute_error += abs(forecast - actual)
    if total_actual == 0:
        history_flags.append("zero_historical_actual")
    wape = absolute_error / total_actual if history_complete and total_actual > 0 else None
    bias = (total_forecast - total_actual) / total_actual if history_complete and total_actual > 0 else None

    seen: set[str] = set()
    missing: list[str] = []
    stages: list[dict[str, Any]] = []
    weighted_total = Decimal(0)
    low_total = Decimal(0)
    high_total = Decimal(0)
    forecast_complete = target is not None
    for index, raw_stage in enumerate(_list(data.get("stages"), "stages")):
        path = f"stages[{index}]"
        stage = _object(raw_stage, path)
        name = _string(stage.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("stage names must be unique")
        seen.add(name)
        amount = _money(stage.get("open_amount"), f"{path}.open_amount", currency)
        deals = _scalar(stage.get("deal_count"), f"{path}.deal_count")
        rate = _rate(_scalar(stage.get("historical_win_rate"), f"{path}.historical_win_rate"), f"{path}.historical_win_rate")
        low = _rate(_scalar(stage.get("low_win_rate"), f"{path}.low_win_rate"), f"{path}.low_win_rate")
        high = _rate(_scalar(stage.get("high_win_rate"), f"{path}.high_win_rate"), f"{path}.high_win_rate")
        sample = _scalar(stage.get("historical_sample"), f"{path}.historical_sample")
        values = {
            "open_amount": amount,
            "deal_count": deals,
            "historical_win_rate": rate,
            "low_win_rate": low,
            "high_win_rate": high,
            "historical_sample": sample,
        }
        for field, value in values.items():
            if value is None:
                missing.append(f"{path}.{field}")
        complete = all(value is not None for value in values.values())
        weighted = low_amount = high_amount = None
        flags: list[str] = []
        if complete:
            assert amount is not None and rate is not None and low is not None and high is not None and sample is not None
            if not low <= rate <= high:
                raise ValueError(f"{path} requires low_win_rate <= historical_win_rate <= high_win_rate")
            weighted = amount * rate
            low_amount = amount * low
            high_amount = amount * high
            weighted_total += weighted
            low_total += low_amount
            high_total += high_amount
            if sample < minimum_sample:
                flags.append("small_historical_sample")
        else:
            forecast_complete = False
        stages.append({
            "name": name,
            "status": "complete" if complete else "indeterminate",
            "weighted_amount": _number(weighted),
            "low_amount": _number(low_amount),
            "high_amount": _number(high_amount),
            "flags": flags,
        })

    if target is None:
        missing.append("target")
    weighted_output = weighted_total if forecast_complete else None
    return {
        "currency": currency,
        "forecast_period": period,
        "history": {"status": "complete" if history_complete else "indeterminate", "wape": _number(wape), "bias_rate": _number(bias), "flags": history_flags},
        "stages": stages,
        "forecast": {
            "status": "complete" if forecast_complete else "indeterminate",
            "weighted_amount": _number(weighted_output),
            "low_amount": _number(low_total) if forecast_complete else None,
            "high_amount": _number(high_total) if forecast_complete else None,
            "target_gap": _number(max(Decimal(0), target - weighted_total)) if forecast_complete and target is not None else None,
            "coverage_rate": _number(weighted_total / target) if forecast_complete and target is not None and target > 0 else None,
        },
        "missing_inputs": sorted(set(missing)),
        "scope": "historical calibration and pipeline range; not a revenue commitment",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: calculate_sales_forecast.py <input.json>", file=sys.stderr)
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
