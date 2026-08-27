#!/usr/bin/env python3
"""Calculate normalized customer concentration and explicitly modeled loss impacts."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from datetime import date
from pathlib import Path
from typing import Any


EVIDENCE = {"confirmed", "reported", "estimated", "unknown"}
EVENTS = {"churn", "contraction", "payment_delay"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
METRICS = ("revenue", "gross_profit", "cash_collections")
NONNEGATIVE_METRICS = {"revenue", "cash_collections"}


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be a finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{path} must be a finite number") from None
    if not result.is_finite():
        raise ValueError(f"{path} must be a finite number")
    return result


def _money(value: object, path: str, *, nonnegative: bool = False) -> Decimal | None:
    money = _object(value, path)
    evidence = money.get("evidence")
    if evidence not in EVIDENCE:
        raise ValueError(f"{path}.evidence must be confirmed, reported, estimated, or unknown")
    amount = money.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path}.amount must be null when evidence is unknown")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount must be known unless evidence is unknown")
    result = _decimal(amount, f"{path}.amount")
    if nonnegative and result < 0:
        raise ValueError(f"{path}.amount must be nonnegative")
    return result


def _rate(value: object, path: str) -> Decimal:
    result = _decimal(value, path)
    if not Decimal("0") <= result <= Decimal("1"):
        raise ValueError(f"{path} must be from 0 through 1")
    return result


def validate(payload: object) -> dict[str, Any]:
    """Validate the input contract and return the normalized payload unchanged."""
    data = _object(payload, "payload")
    try:
        date.fromisoformat(_string(data.get("as_of_date"), "as_of_date"))
    except ValueError:
        raise ValueError("as_of_date must be an ISO date") from None
    _string(data.get("analysis_period"), "analysis_period")
    currency = data.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter code")
    _string(data.get("revenue_basis"), "revenue_basis")

    customers = data.get("customers")
    if not isinstance(customers, list) or not customers:
        raise ValueError("customers must be a nonempty list")
    customer_ids: set[str] = set()
    for index, raw_customer in enumerate(customers):
        customer = _object(raw_customer, f"customer {index}")
        customer_id = _string(customer.get("id"), f"customer {index}.id")
        if customer_id in customer_ids:
            raise ValueError(f"duplicate customer id {customer_id}")
        customer_ids.add(customer_id)
        for metric in METRICS:
            _money(
                customer.get(metric),
                f"customer {customer_id}.{metric}",
                nonnegative=metric in NONNEGATIVE_METRICS,
            )
        for metric in METRICS:
            money = _object(customer[metric], f"customer {customer_id}.{metric}")
            item_currency = money.get("currency", currency)
            if item_currency != currency:
                raise ValueError(f"customer {customer_id}.{metric}.currency must match top-level currency")

    context = _object(data.get("financial_context"), "financial_context")
    _money(context.get("opening_available_cash"), "financial_context.opening_available_cash", nonnegative=True)
    _money(context.get("minimum_cash_buffer"), "financial_context.minimum_cash_buffer", nonnegative=True)
    _money(context.get("baseline_monthly_net_cash_flow"), "financial_context.baseline_monthly_net_cash_flow")
    _money(context.get("fixed_costs"), "financial_context.fixed_costs", nonnegative=True)

    scenarios = data.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")
    scenario_ids: set[str] = set()
    for index, raw_scenario in enumerate(scenarios):
        scenario = _object(raw_scenario, f"scenario {index}")
        scenario_id = _string(scenario.get("id"), f"scenario {index}.id")
        if scenario_id in scenario_ids:
            raise ValueError(f"duplicate scenario id {scenario_id}")
        scenario_ids.add(scenario_id)
        customer_id = _string(scenario.get("customer_id"), f"scenario {scenario_id}.customer_id")
        if customer_id not in customer_ids:
            raise ValueError(f"scenario {scenario_id}.customer_id must reference a known customer")
        event = scenario.get("event")
        if event not in EVENTS:
            raise ValueError(f"scenario {scenario_id}.event must be churn, contraction, or payment_delay")
        if event == "payment_delay":
            if "reduction_rate" in scenario:
                raise ValueError(f"scenario {scenario_id}.reduction_rate is not valid for payment_delay")
        else:
            if "reduction_rate" not in scenario:
                raise ValueError(f"scenario {scenario_id}.reduction_rate is required")
            _rate(scenario["reduction_rate"], f"scenario {scenario_id}.reduction_rate")
        _money(scenario.get("cash_impact_now"), f"scenario {scenario_id}.cash_impact_now", nonnegative=True)
        _money(
            scenario.get("recurring_monthly_cash_impact"),
            f"scenario {scenario_id}.recurring_monthly_cash_impact",
            nonnegative=True,
        )
    return data


def _metric_summary(customers: list[dict[str, Any]], metric: str) -> dict[str, object]:
    values: list[tuple[str, Decimal]] = []
    missing: list[str] = []
    for customer in customers:
        value = _money(customer[metric], f"customer {customer['id']}.{metric}")
        if value is None:
            missing.append(customer["id"])
        else:
            values.append((customer["id"], value))
    known_total = sum((value for _, value in values), Decimal("0"))
    result: dict[str, object] = {
        "known_customer_count": len(values),
        "total_customer_count": len(customers),
        "known_total": known_total,
        "missing_customer_ids": missing,
    }
    if missing:
        result.update({"status": "indeterminate_missing_customer_values", "total": None, "top_n_shares": None, "hhi": None, "customer_shares": None})
        return result
    if metric == "gross_profit" and any(value < 0 for _, value in values):
        result.update({"status": "indeterminate_negative_gross_profit", "total": known_total, "top_n_shares": None, "hhi": None, "customer_shares": None})
        return result
    if known_total <= 0:
        result.update({"status": "indeterminate_nonpositive_total", "total": known_total, "top_n_shares": None, "hhi": None, "customer_shares": None})
        return result
    sorted_values = sorted(values, key=lambda item: (-item[1], item[0]))
    shares = [{"customer_id": customer_id, "share": value / known_total} for customer_id, value in sorted_values]
    result.update(
        {
            "status": "calculated",
            "total": known_total,
            "top_n_shares": {
                str(count): sum((value for _, value in sorted_values[:count]), Decimal("0")) / known_total
                for count in (1, 3, 5, 10)
            },
            "hhi": sum((entry["share"] ** 2 for entry in shares), Decimal("0")) * Decimal("10000"),
            "customer_shares": shares,
        }
    )
    return result


def _context_value(context: dict[str, Any], key: str) -> Decimal | None:
    return _money(context[key], f"financial_context.{key}", nonnegative=key != "baseline_monthly_net_cash_flow")


def _months_to_threshold(cash: Decimal, threshold: Decimal, monthly_flow: Decimal) -> Decimal | str:
    if cash <= threshold:
        return Decimal("0")
    if monthly_flow >= 0:
        return "not_exhausted_under_constant_monthly_model"
    return (cash - threshold) / -monthly_flow


def _scenario_result(
    scenario: dict[str, Any], customers_by_id: dict[str, dict[str, Any]], totals: dict[str, dict[str, object]], context: dict[str, Any]
) -> dict[str, object]:
    customer = customers_by_id[scenario["customer_id"]]
    event = scenario["event"]
    missing: list[str] = []
    if event == "payment_delay":
        revenue_lost = Decimal("0")
        gross_profit_lost = Decimal("0")
    else:
        rate = _rate(scenario["reduction_rate"], f"scenario {scenario['id']}.reduction_rate")
        revenue = _money(customer["revenue"], f"customer {customer['id']}.revenue", nonnegative=True)
        gross_profit = _money(customer["gross_profit"], f"customer {customer['id']}.gross_profit")
        if revenue is None:
            missing.append(f"customer:{customer['id']}.revenue")
            revenue_lost = None
        else:
            revenue_lost = revenue * rate
        if gross_profit is None:
            missing.append(f"customer:{customer['id']}.gross_profit")
            gross_profit_lost = None
        else:
            gross_profit_lost = gross_profit * rate

    total_gross_profit = totals["gross_profit"].get("total")
    fixed_costs = _context_value(context, "fixed_costs")
    if total_gross_profit is None:
        missing.append("total_gross_profit")
    if fixed_costs is None:
        missing.append("financial_context.fixed_costs")
    if gross_profit_lost is None or total_gross_profit is None:
        gross_profit_after = None
        fixed_cost_coverage = None
    else:
        gross_profit_after = total_gross_profit - gross_profit_lost
        fixed_cost_coverage = (
            "not_applicable_zero_fixed_cost" if fixed_costs == 0 else gross_profit_after / fixed_costs
        ) if fixed_costs is not None else None

    now = _money(scenario["cash_impact_now"], f"scenario {scenario['id']}.cash_impact_now", nonnegative=True)
    recurring = _money(scenario["recurring_monthly_cash_impact"], f"scenario {scenario['id']}.recurring_monthly_cash_impact", nonnegative=True)
    opening = _context_value(context, "opening_available_cash")
    buffer = _context_value(context, "minimum_cash_buffer")
    baseline_flow = _context_value(context, "baseline_monthly_net_cash_flow")
    if now is None:
        missing.append(f"scenario:{scenario['id']}.cash_impact_now")
    if recurring is None:
        missing.append(f"scenario:{scenario['id']}.recurring_monthly_cash_impact")
    if opening is None:
        missing.append("financial_context.opening_available_cash")
    if buffer is None:
        missing.append("financial_context.minimum_cash_buffer")
    if baseline_flow is None:
        missing.append("financial_context.baseline_monthly_net_cash_flow")
    if any(value is None for value in (now, recurring, opening, buffer, baseline_flow)):
        cash_after = None
        adjusted_flow = None
        months_to_buffer = None
        months_to_zero = None
    else:
        cash_after = opening - now
        adjusted_flow = baseline_flow - recurring
        months_to_buffer = _months_to_threshold(cash_after, buffer, adjusted_flow)
        months_to_zero = _months_to_threshold(cash_after, Decimal("0"), adjusted_flow)

    return {
        "id": scenario["id"],
        "customer_id": scenario["customer_id"],
        "event": event,
        "reduction_rate": scenario.get("reduction_rate"),
        "revenue_lost": revenue_lost,
        "gross_profit_lost": gross_profit_lost,
        "gross_profit_after_event": gross_profit_after,
        "fixed_cost_coverage_after_event": fixed_cost_coverage,
        "cash_impact_now": now,
        "recurring_monthly_cash_impact": recurring,
        "cash_after_event": cash_after,
        "adjusted_monthly_net_cash_flow": adjusted_flow,
        "months_to_minimum_cash_buffer": months_to_buffer,
        "months_to_zero_cash": months_to_zero,
        "missing_inputs": sorted(set(missing)),
    }


def calculate(payload: object) -> dict[str, object]:
    """Calculate concentration statistics and selected-customer event scenarios."""
    data = validate(payload)
    customers = data["customers"]
    totals = {metric: _metric_summary(customers, metric) for metric in METRICS}
    customers_by_id = {customer["id"]: customer for customer in customers}
    scenarios = [
        _scenario_result(scenario, customers_by_id, totals, data["financial_context"])
        for scenario in data["scenarios"]
    ]
    provisional = any(summary["status"] != "calculated" for summary in totals.values()) or any(
        scenario["missing_inputs"] for scenario in scenarios
    )
    return {
        "as_of_date": data["as_of_date"],
        "analysis_period": data["analysis_period"],
        "currency": data["currency"],
        "revenue_basis": data["revenue_basis"],
        "provisional": provisional,
        "concentration": totals,
        "scenarios": scenarios,
    }


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: calculate_customer_concentration.py <input.json|->", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text(encoding="utf-8")
        result = calculate(json.loads(raw))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
