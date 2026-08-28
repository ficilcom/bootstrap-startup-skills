#!/usr/bin/env python3
"""Measure forecast error and calculate an evidence-bounded pipeline range."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
ANALYSIS_MODES = {"core", "advanced"}


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


def _analysis_mode(value: object) -> str:
    mode = "core" if value is None else value
    if mode not in ANALYSIS_MODES:
        raise ValueError("analysis_mode must be core or advanced")
    return str(mode)


def _iso_date(value: object, path: str) -> date:
    text = _string(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _evidence_counts(value: object) -> dict[str, int]:
    counts = {state: 0 for state in sorted(EVIDENCE_STATES)}

    def visit(item: object) -> None:
        if isinstance(item, dict):
            evidence = item.get("evidence")
            if evidence in counts:
                counts[evidence] += 1
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return counts


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
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
    history_unknowns: list[str] = []
    history_periods: list[dict[str, Any]] = []
    group_totals: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: {"forecast": Decimal(0), "actual": Decimal(0), "absolute_error": Decimal(0)})
    for index, raw_period in enumerate(_list(data.get("history"), "history")):
        path = f"history[{index}]"
        item = _object(raw_period, path)
        history_period = _string(item.get("period"), f"{path}.period")
        forecast = _money(item.get("forecast"), f"{path}.forecast", currency)
        actual = _money(item.get("actual"), f"{path}.actual", currency)
        if forecast is None or actual is None:
            history_complete = False
            if forecast is None:
                history_unknowns.append(f"{path}.forecast")
            if actual is None:
                history_unknowns.append(f"{path}.actual")
            continue
        total_forecast += forecast
        total_actual += actual
        absolute_error += abs(forecast - actual)
        if mode == "advanced":
            segment = _string(item.get("segment", "all"), f"{path}.segment")
            regime = _string(item.get("regime", "current"), f"{path}.regime")
            signed_error = forecast - actual
            history_periods.append({
                "period": history_period,
                "segment": segment,
                "regime": regime,
                "signed_error": _number(signed_error),
                "absolute_error": _number(abs(signed_error)),
            })
            group = group_totals[(segment, regime)]
            group["forecast"] += forecast
            group["actual"] += actual
            group["absolute_error"] += abs(signed_error)
    if total_actual == 0:
        history_flags.append("zero_historical_actual")
    wape = absolute_error / total_actual if history_complete and total_actual > 0 else None
    bias = (total_forecast - total_actual) / total_actual if history_complete and total_actual > 0 else None

    seen: set[str] = set()
    missing: list[str] = []
    stages: list[dict[str, Any]] = []
    stage_inputs: dict[str, dict[str, Decimal | None]] = {}
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
        stage_inputs[name] = {"open_amount": amount, "deal_count": deals, "rate": rate}

    if target is None:
        missing.append("target")
    weighted_output = weighted_total if forecast_complete else None
    calibration_groups: list[dict[str, Any]] = []
    for (segment, regime), totals in sorted(group_totals.items()):
        actual = totals["actual"]
        calibration_groups.append({
            "segment": segment,
            "regime": regime,
            "wape": _number(totals["absolute_error"] / actual) if actual > 0 else None,
            "bias_rate": _number((totals["forecast"] - actual) / actual) if actual > 0 else None,
        })

    decision_unknowns: list[str] = list(history_unknowns)
    opportunity_output: list[dict[str, Any]] = []
    opportunity_reconciliation: list[dict[str, Any]] = []
    customer_amounts: dict[str, Decimal] = defaultdict(Decimal)
    in_period_weighted = Decimal(0)
    if mode == "advanced":
        as_of = _iso_date(data.get("as_of_date"), "as_of_date")
        forecast_end = _iso_date(data.get("forecast_end_date"), "forecast_end_date")
        if forecast_end < as_of:
            raise ValueError("forecast_end_date must not be before as_of_date")
        raw_limits = _object(data.get("stage_age_limits_days"), "stage_age_limits_days")
        age_limits: dict[str, int] = {}
        for stage_name in stage_inputs:
            limit = raw_limits.get(stage_name)
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError(f"stage_age_limits_days.{stage_name} must be a positive integer")
            age_limits[stage_name] = limit
        opportunity_ids: set[str] = set()
        ledger_amounts: dict[str, Decimal] = defaultdict(Decimal)
        ledger_counts: dict[str, int] = defaultdict(int)
        for index, raw_opportunity in enumerate(_list(data.get("opportunities"), "opportunities")):
            path = f"opportunities[{index}]"
            opportunity = _object(raw_opportunity, path)
            opportunity_id = _string(opportunity.get("id"), f"{path}.id")
            if opportunity_id in opportunity_ids:
                raise ValueError("opportunity ids must be unique")
            opportunity_ids.add(opportunity_id)
            customer_id = _string(opportunity.get("customer_id"), f"{path}.customer_id")
            stage_name = _string(opportunity.get("stage"), f"{path}.stage")
            if stage_name not in stage_inputs:
                raise ValueError(f"{path}.stage references unknown stage {stage_name}")
            amount = _money(opportunity.get("amount"), f"{path}.amount", currency)
            entered = _iso_date(opportunity.get("entered_stage_date"), f"{path}.entered_stage_date")
            original_close = _iso_date(opportunity.get("original_close_date"), f"{path}.original_close_date")
            current_close = _iso_date(opportunity.get("current_close_date"), f"{path}.current_close_date")
            next_action = _iso_date(opportunity.get("next_action_date"), f"{path}.next_action_date")
            flags: list[str] = []
            age_days = (as_of - entered).days
            if age_days > age_limits[stage_name]:
                flags.append("stale_stage")
            if current_close > original_close:
                flags.append("close_date_pushed")
            if current_close > forecast_end:
                flags.append("forecast_period_outside")
            if current_close < as_of:
                flags.append("close_date_overdue")
            if next_action < as_of:
                flags.append("next_action_overdue")
            rate = stage_inputs[stage_name]["rate"]
            weighted = amount * rate if amount is not None and rate is not None else None
            if amount is None:
                decision_unknowns.append(f"{path}.amount")
            else:
                customer_amounts[customer_id] += amount
                ledger_amounts[stage_name] += amount
            ledger_counts[stage_name] += 1
            if weighted is not None and as_of <= current_close <= forecast_end:
                in_period_weighted += weighted
            opportunity_output.append({
                "id": opportunity_id,
                "customer_id": customer_id,
                "stage": stage_name,
                "stage_age_days": age_days,
                "weighted_amount": _number(weighted),
                "flags": flags,
            })
        for stage_name in sorted(stage_inputs):
            stage_amount = stage_inputs[stage_name]["open_amount"]
            stage_count = stage_inputs[stage_name]["deal_count"]
            amount_gap = ledger_amounts[stage_name] - stage_amount if stage_amount is not None else None
            count_gap = Decimal(ledger_counts[stage_name]) - stage_count if stage_count is not None else None
            flags: list[str] = []
            if amount_gap is not None and amount_gap != 0:
                flags.append("amount_mismatch")
            if count_gap is not None and count_gap != 0:
                flags.append("deal_count_mismatch")
            opportunity_reconciliation.append({
                "stage": stage_name,
                "amount_gap": _number(amount_gap),
                "deal_count_gap": _number(count_gap),
                "flags": flags,
            })
    total_opportunity_amount = sum(customer_amounts.values(), Decimal(0))
    customer_concentration = [
        {"customer_id": customer_id, "amount": _number(amount), "amount_share": _number(amount / total_opportunity_amount) if total_opportunity_amount > 0 else None}
        for customer_id, amount in sorted(customer_amounts.items(), key=lambda item: (-item[1], item[0]))
    ]
    missing.extend(decision_unknowns)
    if not forecast_complete:
        quality_status = "indeterminate"
    elif missing:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in stages for flag in item["flags"]} | {flag for item in opportunity_output for flag in item["flags"]} | {flag for item in opportunity_reconciliation for flag in item["flags"]})
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
        "history_periods": history_periods,
        "calibration_groups": calibration_groups,
        "opportunity_quality": {"opportunities": opportunity_output, "in_period_weighted_amount": _number(in_period_weighted) if mode == "advanced" else None},
        "opportunity_reconciliation": opportunity_reconciliation,
        "customer_concentration": customer_concentration,
        "analysis_quality": {
            "mode": mode,
            "status": quality_status,
            "evidence_counts": _evidence_counts(data),
            "decision_changing_unknowns": sorted(set(decision_unknowns)),
            "warnings": warnings,
        },
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
