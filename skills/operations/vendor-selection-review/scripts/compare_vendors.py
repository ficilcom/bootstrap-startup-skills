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
ANALYSIS_MODES = {"core", "advanced"}
REQUIREMENT_IMPORTANCE = {"must", "should"}
REQUIREMENT_STATUS = {"verified", "reported", "unknown", "failed"}


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


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    mode = _analysis_mode(data.get("analysis_mode"))
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")
    horizon = data.get("horizon_months")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("horizon_months must be a positive integer")
    hourly_cost = _money(data.get("internal_hourly_cost"), "internal_hourly_cost", currency)

    requirement_importance: dict[str, str] = {}
    if mode == "advanced":
        for index, raw_requirement in enumerate(data.get("requirements", [])):
            path = f"requirements[{index}]"
            requirement = _object(raw_requirement, path)
            requirement_id = _string(requirement.get("id"), f"{path}.id")
            if requirement_id in requirement_importance:
                raise ValueError("requirement ids must be unique")
            importance = requirement.get("importance")
            if importance not in REQUIREMENT_IMPORTANCE:
                raise ValueError(f"{path}.importance must be must or should")
            requirement_importance[requirement_id] = str(importance)

    seen: set[str] = set()
    missing: list[str] = []
    results: list[dict[str, Any]] = []
    decision_unknowns: list[str] = []
    components: dict[str, dict[str, Decimal | int | None]] = {}
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
        advanced: dict[str, Any] = {}
        if mode == "advanced":
            advanced_values: dict[str, Decimal | None] = {}
            for field in (
                "implementation_external_cost",
                "training_hours",
                "monthly_support_cost",
                "renewal_monthly_cost",
                "data_export_cost",
            ):
                raw_value = option.get(field)
                if raw_value is None:
                    value = None
                elif field == "training_hours":
                    value = _scalar(raw_value, f"{path}.{field}")
                else:
                    value = _money(raw_value, f"{path}.{field}", currency)
                advanced_values[field] = value
                if value is None:
                    decision_unknowns.append(f"{path}.{field}")
            renewal_start = option.get("renewal_start_month")
            if isinstance(renewal_start, bool) or not isinstance(renewal_start, int) or not 1 <= renewal_start <= horizon:
                raise ValueError(f"{path}.renewal_start_month must be between 1 and horizon_months")
            result_statuses: dict[str, str] = {}
            for result_index, raw_result in enumerate(option.get("requirement_results", [])):
                result_path = f"{path}.requirement_results[{result_index}]"
                requirement_result = _object(raw_result, result_path)
                requirement_id = _string(requirement_result.get("id"), f"{result_path}.id")
                if requirement_id not in requirement_importance:
                    raise ValueError(f"{result_path} references unknown requirement {requirement_id}")
                if requirement_id in result_statuses:
                    raise ValueError(f"{path}.requirement_results ids must be unique")
                status_value = requirement_result.get("status")
                if status_value not in REQUIREMENT_STATUS:
                    raise ValueError(f"{result_path}.status must be supported")
                result_statuses[requirement_id] = str(status_value)
            failed_gates = sorted(requirement_id for requirement_id, importance in requirement_importance.items() if importance == "must" and result_statuses.get(requirement_id) == "failed")
            unverified_gates = sorted(requirement_id for requirement_id in requirement_importance if result_statuses.get(requirement_id) != "verified" and requirement_id not in failed_gates)
            for requirement_id in unverified_gates:
                decision_unknowns.append(f"{path}.requirements.{requirement_id}")
            eligibility = "disqualified" if failed_gates else "conditional" if unverified_gates else "eligible"
            implementation = advanced_values["implementation_external_cost"]
            training = advanced_values["training_hours"]
            support = advanced_values["monthly_support_cost"]
            renewal = advanced_values["renewal_monthly_cost"]
            export = advanced_values["data_export_cost"]
            advanced_complete = complete and all(value is not None for value in advanced_values.values())
            advanced_tco = None
            if advanced_complete:
                assert all(value is not None for value in (initial, monthly, usage, migration_hours, exit_cost, hourly_cost, implementation, training, support, renewal, export))
                before = renewal_start - 1
                after = horizon - before
                advanced_tco = initial + migration_hours * hourly_cost + exit_cost + implementation + training * hourly_cost + support * horizon + export + monthly * before + renewal * after + usage * horizon
            components[name] = {
                "initial": initial,
                "monthly": monthly,
                "usage": usage,
                "migration_hours": migration_hours,
                "exit": exit_cost,
                "implementation": implementation,
                "training": training,
                "support": support,
                "renewal": renewal,
                "renewal_start": renewal_start,
                "export": export,
            }
            advanced = {
                "advanced_horizon_tco": _number(advanced_tco),
                "eligibility_status": eligibility,
                "failed_gates": failed_gates,
                "unverified_gates": unverified_gates,
            }
            if failed_gates:
                flags.append("failed_must_requirement")
            if unverified_gates:
                flags.append("unverified_requirements")
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
            **advanced,
        })

    comparable = [item for item in results if item["horizon_tco"] is not None]
    comparable.sort(key=lambda item: (item["horizon_tco"], item["name"]))
    scenario_tco: list[dict[str, Any]] = []
    if mode == "advanced":
        scenario_names: set[str] = set()
        for scenario_index, raw_scenario in enumerate(data.get("scenarios", [])):
            scenario_path = f"scenarios[{scenario_index}]"
            scenario = _object(raw_scenario, scenario_path)
            scenario_name = _string(scenario.get("name"), f"{scenario_path}.name")
            if scenario_name in scenario_names:
                raise ValueError("scenario names must be unique")
            scenario_names.add(scenario_name)
            overrides: dict[str, dict[str, Decimal | None]] = {}
            for override_index, raw_override in enumerate(scenario.get("option_overrides", [])):
                override_path = f"{scenario_path}.option_overrides[{override_index}]"
                override = _object(raw_override, override_path)
                option_name = _string(override.get("name"), f"{override_path}.name")
                if option_name not in seen:
                    raise ValueError(f"{override_path} references unknown option {option_name}")
                if option_name in overrides:
                    raise ValueError(f"{scenario_path}.option_overrides names must be unique")
                overrides[option_name] = {
                    "monthly": _money(override["monthly_cost"], f"{override_path}.monthly_cost", currency) if "monthly_cost" in override else None,
                    "usage": _money(override["monthly_usage_cost"], f"{override_path}.monthly_usage_cost", currency) if "monthly_usage_cost" in override else None,
                }
            scenario_options: dict[str, int | float | None] = {}
            for option_name in sorted(seen):
                part = components[option_name]
                required_values = [part[key] for key in ("initial", "monthly", "usage", "migration_hours", "exit", "implementation", "training", "support", "renewal", "export")]
                if hourly_cost is None or any(value is None for value in required_values):
                    scenario_options[option_name] = None
                    continue
                override = overrides.get(option_name, {})
                monthly_override = override.get("monthly")
                usage_override = override.get("usage")
                monthly_value = part["monthly"] if monthly_override is None else monthly_override
                usage_value = part["usage"] if usage_override is None else usage_override
                before = int(part["renewal_start"]) - 1
                after = horizon - before
                total = part["initial"] + part["migration_hours"] * hourly_cost + part["exit"] + part["implementation"] + part["training"] * hourly_cost + part["support"] * horizon + part["export"] + monthly_value * before + part["renewal"] * after + usage_value * horizon
                scenario_options[option_name] = _number(total)
            scenario_tco.append({"name": scenario_name, "options": scenario_options})

    if not comparable:
        quality_status = "indeterminate"
    elif missing or decision_unknowns:
        quality_status = "partial"
    else:
        quality_status = "complete"
    warnings = sorted({flag for item in results for flag in item["flags"]})
    return {
        "currency": currency,
        "horizon_months": horizon,
        "options": results,
        "cost_order": [item["name"] for item in comparable],
        "missing_inputs": sorted(set(missing)),
        "ranking_scope": "quantified total cost only; fit, reliability, security, lock-in, and contract risk remain separate",
        "scenario_tco": scenario_tco,
        "negotiation_points": sorted(set(decision_unknowns)),
        "validation_targets": sorted(set(decision_unknowns)),
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
