#!/usr/bin/env python3
"""Compare quarterly capital proposals and user-defined portfolios under cash scenarios."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
STRATEGIC_FIT = {"required_guardrail", "supports_priority", "optional", "unclear", "conflicts"}
REVERSIBILITY = {"high", "medium", "low"}
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


def _date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _decimal(value: object, path: str, *, allow_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{path} must be numeric") from error
    if not result.is_finite() or (result < 0 and not allow_negative):
        raise ValueError(f"{path} must be {'finite' if allow_negative else 'non-negative'}")
    return result


def _money(
    value: object, path: str, currency: str, *, allow_negative: bool = False
) -> Decimal | None:
    item = _object(value, path)
    evidence = item.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be supported")
    if item.get("currency") != currency:
        raise ValueError(f"{path}.currency must match currency")
    amount = item.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path}.amount must be null when evidence is unknown")
        return None
    if amount is None:
        raise ValueError(f"{path}.amount is required unless evidence is unknown")
    return _decimal(amount, f"{path}.amount", allow_negative=allow_negative)


def _money_series(
    value: object,
    path: str,
    currency: str,
    months: int,
    *,
    allow_negative: bool = False,
) -> list[Decimal | None]:
    values = _list(value, path)
    if len(values) != months:
        raise ValueError(f"{path} must contain quarter_months entries")
    return [
        _money(item, f"{path}[{index}]", currency, allow_negative=allow_negative)
        for index, item in enumerate(values)
    ]


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("0.000001"))
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def _scenario(
    opening: Decimal,
    buffer: Decimal,
    baseline: list[Decimal],
    proposals: list[dict[str, Any]],
    case: str,
) -> dict[str, Any]:
    upfront = sum((proposal["upfront_cost"] for proposal in proposals), Decimal(0))
    cash = opening - upfront
    minimum_cash = cash
    breach = 0 if cash < buffer else None
    cumulative_investment = -upfront
    payback = None
    monthly_cash: list[int | float] = []
    total_benefit = total_monthly_cost = total_extra_cost = Decimal(0)
    for month, baseline_flow in enumerate(baseline, start=1):
        benefit_key = "base_benefits" if case == "base" else "downside_benefits"
        benefits = sum((proposal[benefit_key][month - 1] for proposal in proposals), Decimal(0))
        monthly_costs = sum((proposal["monthly_costs"][month - 1] for proposal in proposals), Decimal(0))
        extra_costs = (
            sum((proposal["downside_extra_costs"][month - 1] for proposal in proposals), Decimal(0))
            if case == "downside"
            else Decimal(0)
        )
        cash += baseline_flow + benefits - monthly_costs - extra_costs
        cumulative_investment += benefits - monthly_costs - extra_costs
        total_benefit += benefits
        total_monthly_cost += monthly_costs
        total_extra_cost += extra_costs
        minimum_cash = min(minimum_cash, cash)
        if breach is None and cash < buffer:
            breach = month
        if payback is None and cumulative_investment >= 0:
            payback = month
        monthly_cash.append(_number(cash))
    net_effect = total_benefit - upfront - total_monthly_cost - total_extra_cost
    return {
        "ending_cash": _number(cash),
        "minimum_cash": _number(minimum_cash),
        "buffer_breach_month": breach,
        "net_cash_effect": _number(net_effect),
        "payback_month": payback,
        "monthly_ending_cash": monthly_cash,
    }


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    as_of = _date(data.get("as_of_date"), "as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    months = data.get("quarter_months")
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise ValueError("quarter_months must be a positive integer")
    opening = _money(data.get("opening_cash"), "opening_cash", currency)
    buffer = _money(data.get("minimum_cash_buffer"), "minimum_cash_buffer", currency)
    baseline_values = _money_series(
        data.get("baseline_net_cash_by_month"),
        "baseline_net_cash_by_month",
        currency,
        months,
        allow_negative=True,
    )
    global_complete = opening is not None and buffer is not None and all(value is not None for value in baseline_values)
    baseline = [value for value in baseline_values if value is not None]
    missing: list[str] = []
    if opening is None:
        missing.append("opening_cash")
    if buffer is None:
        missing.append("minimum_cash_buffer")
    for index, value in enumerate(baseline_values):
        if value is None:
            missing.append(f"baseline_net_cash_by_month[{index}]")

    proposals_by_name: dict[str, dict[str, Any]] = {}
    proposal_results: list[dict[str, Any]] = []
    for index, raw_proposal in enumerate(_list(data.get("proposals"), "proposals")):
        path = f"proposals[{index}]"
        proposal = _object(raw_proposal, path)
        name = _string(proposal.get("name"), f"{path}.name")
        if name in proposals_by_name:
            raise ValueError("proposal names must be unique")
        strategic_fit = proposal.get("strategic_fit")
        if strategic_fit not in STRATEGIC_FIT:
            raise ValueError(f"{path}.strategic_fit is invalid")
        reversibility = proposal.get("reversibility")
        if reversibility not in REVERSIBILITY:
            raise ValueError(f"{path}.reversibility is invalid")
        upfront = _money(proposal.get("upfront_cost"), f"{path}.upfront_cost", currency)
        monthly = _money_series(proposal.get("monthly_costs"), f"{path}.monthly_costs", currency, months)
        base_benefits = _money_series(proposal.get("base_benefits"), f"{path}.base_benefits", currency, months)
        downside_benefits = _money_series(
            proposal.get("downside_benefits"), f"{path}.downside_benefits", currency, months
        )
        downside_extra = _money_series(
            proposal.get("downside_extra_costs"), f"{path}.downside_extra_costs", currency, months
        )
        dependencies = _list(proposal.get("dependencies", []), f"{path}.dependencies")
        if any(not isinstance(item, str) or not item.strip() for item in dependencies):
            raise ValueError(f"{path}.dependencies must contain non-empty strings")
        overlap = proposal.get("benefit_overlap_group")
        if overlap is not None and (not isinstance(overlap, str) or not overlap.strip()):
            raise ValueError(f"{path}.benefit_overlap_group must be a non-empty string")
        values = [upfront, *monthly, *base_benefits, *downside_benefits, *downside_extra]
        complete = global_complete and all(value is not None for value in values)
        for field, series in (
            ("monthly_costs", monthly),
            ("base_benefits", base_benefits),
            ("downside_benefits", downside_benefits),
            ("downside_extra_costs", downside_extra),
        ):
            for series_index, value in enumerate(series):
                if value is None:
                    missing.append(f"{path}.{field}[{series_index}]")
        if upfront is None:
            missing.append(f"{path}.upfront_cost")
        normalized = {
            "name": name,
            "upfront_cost": upfront,
            "monthly_costs": monthly,
            "base_benefits": base_benefits,
            "downside_benefits": downside_benefits,
            "downside_extra_costs": downside_extra,
            "strategic_fit": strategic_fit,
            "reversibility": reversibility,
            "dependencies": dependencies,
            "benefit_overlap_group": overlap.strip() if isinstance(overlap, str) else None,
            "complete": complete,
        }
        proposals_by_name[name] = normalized
        base_result = downside_result = None
        if complete:
            assert opening is not None and buffer is not None
            base_result = _scenario(opening, buffer, baseline, [normalized], "base")
            downside_result = _scenario(opening, buffer, baseline, [normalized], "downside")
        proposal_results.append(
            {
                "name": name,
                "status": "complete" if complete else "indeterminate",
                "strategic_fit": strategic_fit,
                "reversibility": reversibility,
                "dependencies": dependencies,
                "base": base_result,
                "downside": downside_result,
            }
        )

    portfolio_results: list[dict[str, Any]] = []
    seen_portfolios: set[str] = set()
    for index, raw_portfolio in enumerate(_list(data.get("portfolios"), "portfolios")):
        path = f"portfolios[{index}]"
        portfolio = _object(raw_portfolio, path)
        name = _string(portfolio.get("name"), f"{path}.name")
        if name in seen_portfolios:
            raise ValueError("portfolio names must be unique")
        seen_portfolios.add(name)
        member_names = _list(portfolio.get("proposals"), f"{path}.proposals")
        if not member_names or any(not isinstance(item, str) or not item for item in member_names):
            raise ValueError(f"{path}.proposals must contain proposal names")
        if len(member_names) != len(set(member_names)):
            raise ValueError(f"{path}.proposals cannot contain duplicate members")
        if any(member not in proposals_by_name for member in member_names):
            raise ValueError(f"{path}.proposals must reference a known proposal")
        members = [proposals_by_name[member] for member in member_names]
        complete = global_complete and all(member["complete"] for member in members)
        flags: list[str] = []
        overlap_groups = [member["benefit_overlap_group"] for member in members if member["benefit_overlap_group"]]
        if len(overlap_groups) != len(set(overlap_groups)):
            flags.append("benefit_overlap_requires_validation")
        base_result = downside_result = None
        affordable = None
        if complete:
            assert opening is not None and buffer is not None
            base_result = _scenario(opening, buffer, baseline, members, "base")
            downside_result = _scenario(opening, buffer, baseline, members, "downside")
            affordable = (
                base_result["buffer_breach_month"] is None
                and downside_result["buffer_breach_month"] is None
            )
        portfolio_results.append(
            {
                "name": name,
                "status": "complete" if complete else "indeterminate",
                "proposals": member_names,
                "base": base_result,
                "downside": downside_result,
                "affordable_in_base_and_downside": affordable,
                "flags": flags,
            }
        )

    affordable_results = [
        item for item in portfolio_results if item["affordable_in_base_and_downside"] is True
    ]
    affordable_results.sort(key=lambda item: (-item["base"]["net_cash_effect"], item["name"]))
    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "quarter_months": months,
        "proposals": proposal_results,
        "portfolios": portfolio_results,
        "affordable_portfolios": [item["name"] for item in affordable_results],
        "comparison_scope": "quantified cash resilience only; strategic fit, option value, dependencies, and unpriced benefits remain separate",
        "missing_inputs": sorted(set(missing)),
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: compare_allocations.py <input.json>", file=sys.stderr)
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
