#!/usr/bin/env python3
"""Analyze offer-level contribution, delivery capacity, and strategic-fit signals."""

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


def _rate(value: object, path: str) -> Decimal:
    result = _decimal(value, path)
    if result > 1:
        raise ValueError(f"{path} must be between 0 and 1")
    return result


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
    period = _string(data.get("period"), "period")
    available = _scalar(data.get("available_delivery_hours"), "available_delivery_hours")
    thresholds = _object(data.get("thresholds"), "thresholds")
    minimum_margin = _rate(thresholds.get("minimum_margin_rate"), "thresholds.minimum_margin_rate")
    heavy_share = _rate(thresholds.get("capacity_heavy_share"), "thresholds.capacity_heavy_share")

    seen: set[str] = set()
    missing: list[str] = []
    results: list[dict[str, Any]] = []
    total_revenue = Decimal(0)
    total_contribution = Decimal(0)
    total_hours = Decimal(0)
    portfolio_complete = available is not None

    for index, raw_offer in enumerate(_list(data.get("offers"), "offers")):
        path = f"offers[{index}]"
        offer = _object(raw_offer, path)
        name = _string(offer.get("name"), f"{path}.name")
        if name in seen:
            raise ValueError("offer names must be unique")
        seen.add(name)
        revenue = _money(offer.get("revenue"), f"{path}.revenue", currency)
        variable_cost = _money(offer.get("variable_cost"), f"{path}.variable_cost", currency)
        hours = _scalar(offer.get("delivery_hours"), f"{path}.delivery_hours")
        fit = _scalar(offer.get("strategic_fit"), f"{path}.strategic_fit")
        if fit is not None and fit > 5:
            raise ValueError(f"{path}.strategic_fit must be between 0 and 5")
        for field, value in (("revenue", revenue), ("variable_cost", variable_cost), ("delivery_hours", hours)):
            if value is None:
                missing.append(f"{path}.{field}")
        if fit is None:
            missing.append(f"{path}.strategic_fit")

        complete = all(value is not None for value in (revenue, variable_cost, hours))
        contribution = margin = per_hour = capacity_share = None
        flags: list[str] = []
        if complete:
            assert revenue is not None and variable_cost is not None and hours is not None
            contribution = revenue - variable_cost
            margin = contribution / revenue if revenue > 0 else None
            per_hour = contribution / hours if hours > 0 else None
            capacity_share = hours / available if available is not None and available > 0 else None
            total_revenue += revenue
            total_contribution += contribution
            total_hours += hours
            if contribution < 0:
                flags.append("negative_contribution")
            if margin is not None and margin < minimum_margin:
                flags.append("below_minimum_margin")
            if hours == 0:
                flags.append("zero_delivery_hours")
            if capacity_share is not None and capacity_share > heavy_share:
                flags.append("capacity_heavy")
        else:
            portfolio_complete = False
        if fit is not None and fit <= 1:
            flags.append("low_strategic_fit")

        results.append({
            "name": name,
            "status": "complete" if complete else "indeterminate",
            "contribution": _number(contribution),
            "contribution_margin_rate": _number(margin),
            "contribution_per_delivery_hour": _number(per_hour),
            "capacity_share": _number(capacity_share),
            "strategic_fit": _number(fit),
            "flags": flags,
        })

    if available is None:
        missing.append("available_delivery_hours")
    comparable = [item for item in results if item["contribution_per_delivery_hour"] is not None]
    comparable.sort(key=lambda item: (-item["contribution_per_delivery_hour"], item["name"]))
    return {
        "currency": currency,
        "period": period,
        "offers": results,
        "portfolio": {
            "status": "complete" if portfolio_complete else "indeterminate",
            "total_revenue": _number(total_revenue) if portfolio_complete else None,
            "total_contribution": _number(total_contribution) if portfolio_complete else None,
            "total_delivery_hours": _number(total_hours) if portfolio_complete else None,
            "unused_delivery_hours": _number(available - total_hours) if portfolio_complete and available is not None else None,
        },
        "economic_order": [item["name"] for item in comparable],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "economic metrics only; strategic fit, demand, and execution risk remain separate",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_offer_portfolio.py <input.json>", file=sys.stderr)
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
