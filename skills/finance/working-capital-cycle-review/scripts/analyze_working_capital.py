#!/usr/bin/env python3
"""Calculate working-capital cycles and user-defined cash-release scenarios."""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
ANALYSIS_MODES = {"core", "advanced"}
BALANCE_BASES = {"average", "ending"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
BALANCE_FIELDS = ("revenue", "cost_of_goods_sold", "accounts_receivable", "inventory", "accounts_payable", "customer_deposits")


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


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


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


def _metrics(values: dict[str, Decimal | None], days: int) -> tuple[dict[str, Decimal | None], list[str]]:
    revenue = values["revenue"]
    cogs = values["cost_of_goods_sold"]
    receivables = values["accounts_receivable"]
    inventory = values["inventory"]
    payables = values["accounts_payable"]
    deposits = values["customer_deposits"]
    warnings: list[str] = []
    dso = None
    if revenue is not None and receivables is not None:
        if revenue == 0:
            warnings.append("zero_revenue_base")
        else:
            dso = receivables / revenue * days
    dio = dpo = None
    if cogs is not None:
        if cogs == 0:
            warnings.append("zero_cogs_base")
        else:
            if inventory is not None:
                dio = inventory / cogs * days
            if payables is not None:
                dpo = payables / cogs * days
    ccc = dso + dio - dpo if dso is not None and dio is not None and dpo is not None else None
    nwc = receivables + inventory - payables - deposits if all(value is not None for value in (receivables, inventory, payables, deposits)) else None
    return {"dso_days": dso, "dio_days": dio, "dpo_days": dpo, "cash_conversion_cycle_days": ccc, "net_working_capital": nwc}, warnings


def _serialized_metrics(metrics: dict[str, Decimal | None]) -> dict[str, int | float | None]:
    return {key: _number(value) for key, value in metrics.items()}


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    measurement_days = _positive_integer(data.get("measurement_days"), "measurement_days")
    balance_basis = data.get("balance_basis")
    if balance_basis not in BALANCE_BASES:
        raise ValueError("balance_basis must be average or ending")

    values: dict[str, Decimal | None] = {}
    decision_unknowns: list[str] = []
    for field in BALANCE_FIELDS:
        value = _money(data.get(field), field, currency)
        values[field] = value
        if value is None:
            decision_unknowns.append(field)
    base_metrics, warnings = _metrics(values, measurement_days)

    cash_release: dict[str, Decimal | None] = {}
    scenario_metrics: list[dict[str, Any]] = []
    validation_targets: list[str] = []
    if mode == "advanced":
        targets = _object(data.get("targets", {}), "targets")
        target_values: dict[str, Decimal | None] = {}
        for field in ("dso_days", "dio_days", "dpo_days"):
            raw = targets.get(field)
            value = None if raw is None else _scalar(raw, f"targets.{field}")
            target_values[field] = value
            if value is None:
                decision_unknowns.append(f"targets.{field}")
        raw_deposits = targets.get("customer_deposits")
        target_deposits = None if raw_deposits is None else _money(raw_deposits, "targets.customer_deposits", currency)
        if target_deposits is None:
            decision_unknowns.append("targets.customer_deposits")

        revenue = values["revenue"]
        cogs = values["cost_of_goods_sold"]
        receivables = values["accounts_receivable"]
        inventory = values["inventory"]
        payables = values["accounts_payable"]
        deposits = values["customer_deposits"]
        receivables_release = None if revenue in {None, Decimal(0)} or receivables is None or target_values["dso_days"] is None else receivables - revenue / measurement_days * target_values["dso_days"]
        inventory_release = None if cogs in {None, Decimal(0)} or inventory is None or target_values["dio_days"] is None else inventory - cogs / measurement_days * target_values["dio_days"]
        payables_release = None if cogs in {None, Decimal(0)} or payables is None or target_values["dpo_days"] is None else cogs / measurement_days * target_values["dpo_days"] - payables
        deposits_release = None if deposits is None or target_deposits is None else target_deposits - deposits
        components = [receivables_release, inventory_release, payables_release, deposits_release]
        total_release = sum(components, Decimal(0)) if all(value is not None for value in components) else None
        cash_release = {"receivables": receivables_release, "inventory": inventory_release, "payables": payables_release, "customer_deposits": deposits_release, "total": total_release}
        validation_targets = [key for key, value in cash_release.items() if key != "total" and value is not None and value != 0]

        scenario_ids: set[str] = set()
        for index, raw_scenario in enumerate(_list(data.get("scenarios", []), "scenarios")):
            path = f"scenarios[{index}]"
            scenario = _object(raw_scenario, path)
            scenario_id = _string(scenario.get("id"), f"{path}.id")
            if scenario_id in scenario_ids:
                raise ValueError("scenario ids must be unique")
            scenario_ids.add(scenario_id)
            scenario_values: dict[str, Decimal | None] = {}
            for field in BALANCE_FIELDS:
                value = _money(scenario.get(field), f"{path}.{field}", currency)
                scenario_values[field] = value
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            metrics, scenario_warnings = _metrics(scenario_values, measurement_days)
            warnings.extend(f"{scenario_id}:{warning}" for warning in scenario_warnings)
            scenario_metrics.append({"id": scenario_id, **_serialized_metrics(metrics)})

    serialized_release = {key: _number(value) for key, value in cash_release.items()}
    unknowns = sorted(set(decision_unknowns))
    available_metrics = sum(value is not None for value in base_metrics.values())
    if available_metrics == 0:
        quality_status = "indeterminate"
    elif unknowns or warnings:
        quality_status = "partial"
    else:
        quality_status = "complete"
    return {
        "currency": currency,
        "measurement_days": measurement_days,
        "balance_basis": balance_basis,
        "base_metrics": _serialized_metrics(base_metrics),
        "cash_release_components": serialized_release,
        "scenario_metrics": scenario_metrics,
        "validation_targets": sorted(validation_targets),
        "interpretation_scope": "signed cash release from user-defined balance targets; feasibility, timing, bad debt, stockouts, supplier impact, tax, and accounting treatment remain separate",
        "analysis_quality": {"mode": mode, "status": quality_status, "evidence_counts": _evidence_counts(data), "decision_changing_unknowns": unknowns, "warnings": sorted(set(warnings))},
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: analyze_working_capital.py <input.json>", file=sys.stderr)
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
