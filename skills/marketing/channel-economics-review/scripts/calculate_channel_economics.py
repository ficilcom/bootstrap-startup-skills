#!/usr/bin/env python3
"""Compare blended and marginal acquisition-channel economics."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
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


def _evidenced(
    value: object, path: str, field: str, *, currency: str | None = None
) -> tuple[Decimal | None, str]:
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
        return None, evidence
    if raw is None:
        raise ValueError(f"{path}.{field} is required unless evidence is unknown")
    return _decimal(raw, f"{path}.{field}"), evidence


def _money(value: object, path: str, currency: str) -> Decimal | None:
    return _evidenced(value, path, "amount", currency=currency)[0]


def _scalar(value: object, path: str) -> Decimal | None:
    return _evidenced(value, path, "value")[0]


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def _horizon_factor(retention: Decimal, horizon: int) -> Decimal:
    return sum((retention**period for period in range(horizon)), Decimal(0))


def _payback(cac: Decimal, contribution: Decimal, retention: Decimal, horizon: int) -> int | None:
    cumulative = Decimal(0)
    for period in range(1, horizon + 1):
        cumulative += contribution * (retention ** (period - 1))
        if cumulative >= cac:
            return period
    return None


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    period_unit = data.get("period_unit")
    if period_unit not in PERIOD_UNITS:
        raise ValueError("period_unit must be week, month, quarter, or year")
    horizon = data.get("horizon_periods")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("horizon_periods must be a positive integer")

    seen: set[str] = set()
    missing: list[str] = []
    results: list[dict[str, Any]] = []
    for index, raw_channel in enumerate(_list(data.get("channels"), "channels")):
        path = f"channels[{index}]"
        channel = _object(raw_channel, path)
        name = _string(channel.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("channel names must be unique")
        seen.add(name)
        spend = _money(channel.get("spend"), f"{path}.spend", currency)
        customers = _scalar(channel.get("acquired_customers"), f"{path}.acquired_customers")
        contribution = _money(
            channel.get("contribution_per_customer_per_period"),
            f"{path}.contribution_per_customer_per_period",
            currency,
        )
        retention = _scalar(channel.get("retention_rate_per_period"), f"{path}.retention_rate_per_period")
        capacity = _scalar(channel.get("capacity_new_customers"), f"{path}.capacity_new_customers")
        if retention is not None and not Decimal(0) <= retention <= Decimal(1):
            raise ValueError(f"{path}.retention_rate_per_period must be between 0 and 1")
        for field, value in (
            ("spend", spend),
            ("acquired_customers", customers),
            ("contribution_per_customer_per_period", contribution),
            ("retention_rate_per_period", retention),
        ):
            if value is None:
                missing.append(f"{path}.{field}")

        flags: list[str] = []
        if customers == 0:
            flags.append("zero_acquisitions")
        if capacity is not None and customers is not None and customers > capacity:
            flags.append("capacity_exceeded")

        complete = all(value is not None for value in (spend, customers, contribution, retention))
        cac = horizon_contribution = net = None
        payback = None
        if complete:
            assert spend is not None and customers is not None and contribution is not None and retention is not None
            if customers > 0:
                cac = spend / customers
                payback = _payback(cac, contribution, retention, horizon)
            horizon_contribution = customers * contribution * _horizon_factor(retention, horizon)
            net = horizon_contribution - spend

        marginal_cac = marginal_contribution = marginal_net = None
        marginal_payback = None
        marginal = channel.get("marginal_case")
        if marginal is not None:
            marginal_data = _object(marginal, f"{path}.marginal_case")
            marginal_spend = _money(
                marginal_data.get("incremental_spend"), f"{path}.marginal_case.incremental_spend", currency
            )
            marginal_customers = _scalar(
                marginal_data.get("incremental_customers"), f"{path}.marginal_case.incremental_customers"
            )
            if marginal_spend is None:
                missing.append(f"{path}.marginal_case.incremental_spend")
            if marginal_customers is None:
                missing.append(f"{path}.marginal_case.incremental_customers")
            if (
                marginal_spend is not None
                and marginal_customers is not None
                and marginal_customers > 0
                and contribution is not None
                and retention is not None
            ):
                marginal_cac = marginal_spend / marginal_customers
                marginal_payback = _payback(marginal_cac, contribution, retention, horizon)
                marginal_contribution = marginal_customers * contribution * _horizon_factor(retention, horizon)
                marginal_net = marginal_contribution - marginal_spend
            elif marginal_customers == 0:
                flags.append("zero_marginal_acquisitions")

        results.append(
            {
                "name": name,
                "status": "complete" if complete else "indeterminate",
                "cac": _number(cac),
                "payback_periods": payback,
                "horizon_contribution": _number(horizon_contribution),
                "horizon_net_contribution": _number(net),
                "marginal_cac": _number(marginal_cac),
                "marginal_payback_periods": marginal_payback,
                "marginal_horizon_contribution": _number(marginal_contribution),
                "marginal_horizon_net_contribution": _number(marginal_net),
                "flags": flags,
            }
        )

    comparable = [
        item
        for item in results
        if item["status"] == "complete" and item["marginal_horizon_net_contribution"] is not None
    ]
    comparable.sort(key=lambda item: (-item["marginal_horizon_net_contribution"], item["name"]))
    return {
        "currency": currency,
        "period_unit": period_unit,
        "horizon_periods": horizon,
        "channels": results,
        "economic_order": [item["name"] for item in comparable],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "marginal quantified economics only; capacity, attribution, and strategic fit remain separate",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: calculate_channel_economics.py <input.json>", file=sys.stderr)
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
