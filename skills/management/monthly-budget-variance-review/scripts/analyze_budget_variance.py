#!/usr/bin/env python3
"""Separate monthly budget variances by triage stage and decompose price, volume, and mix."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
STAGE_ORDER = ("data_quality", "definition_change", "timing", "mix", "real_change")
STAGE_VALUES = {"cleared", "explains", "unresolved", "not_checked"}
BLOCKING_VALUES = {"unresolved", "not_checked"}
STATEMENT_SECTIONS = {"revenue", "cogs", "opex", "other"}
FAVORABLE_DIRECTIONS = {"higher", "lower"}
CLOSE_STATES = {"preliminary", "final"}
COMPARISON_BASES = {"budget", "forecast", "prior_year", "prior_period"}
MATERIALITY_RULES = {"either", "both", "absolute_only", "relative_only"}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
PERCENT_UNIT = Decimal("0.000001")


def _require_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _require_enum(value: object, path: str, allowed: set[str] | tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError(f"{path} must be one of {', '.join(sorted(allowed))}")
    return str(value)


def _parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO date") from error


def _number(value: object, path: str, *, allow_negative: bool) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{path} must be finite")
    if number < 0 and not allow_negative:
        raise ValueError(f"{path} must be nonnegative")
    return number


def _evidence_entry(
    value: object, path: str, key: str, *, allow_negative: bool = False
) -> Decimal | None:
    entry = _require_object(value, path)
    evidence = _require_enum(entry.get("evidence"), f"{path}.evidence", EVIDENCE_STATES)
    raw = entry.get(key)
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown {key} must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.{key} is required when evidence is known")
    return _number(raw, f"{path}.{key}", allow_negative=allow_negative)


def _money(value: object, path: str, *, allow_negative: bool = False) -> Decimal | None:
    return _evidence_entry(value, path, "amount", allow_negative=allow_negative)


def _scalar(value: object, path: str, *, allow_negative: bool = False) -> Decimal | None:
    return _evidence_entry(value, path, "value", allow_negative=allow_negative)


def _percent(value: Decimal, base: Decimal) -> Decimal:
    return (value / base * Decimal(100)).quantize(PERCENT_UNIT)


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _parse_materiality_policy(payload: dict[str, Any], missing: list[str]) -> dict[str, Any] | None:
    if "materiality_policy" not in payload:
        return None
    path = "materiality_policy"
    policy = _require_object(payload.get(path), path)
    absolute = _money(policy.get("absolute"), f"{path}.absolute")
    relative = _scalar(policy.get("relative_percent"), f"{path}.relative_percent")
    rule = _require_enum(policy.get("rule"), f"{path}.rule", MATERIALITY_RULES)
    if absolute is None:
        missing.append(f"{path}.absolute")
    if relative is None:
        missing.append(f"{path}.relative_percent")
    return {"absolute": absolute, "relative_percent": relative, "rule": rule}


def _materiality(
    *,
    variance: Decimal | None,
    budget: Decimal | None,
    variance_percent: Decimal | None,
    line_threshold: Decimal | None,
    policy: dict[str, Any] | None,
) -> tuple[bool | None, str]:
    if variance is None:
        return None, "indeterminate"
    if line_threshold is not None:
        return abs(variance) >= line_threshold, "line_threshold"
    if budget == 0:
        return variance != 0, "zero_budget"
    if policy is None:
        return None, "indeterminate"
    absolute, relative, rule = policy["absolute"], policy["relative_percent"], policy["rule"]
    absolute_hit = None if absolute is None else abs(variance) >= absolute
    relative_hit = (
        None if relative is None or variance_percent is None else abs(variance_percent) >= relative
    )
    if rule == "absolute_only":
        return absolute_hit, "policy"
    if rule == "relative_only":
        return relative_hit, "policy"
    if rule == "either":
        if absolute_hit or relative_hit:
            return True, "policy"
        if absolute_hit is None or relative_hit is None:
            return None, "indeterminate"
        return False, "policy"
    if absolute_hit is None or relative_hit is None:
        return None, "indeterminate"
    return absolute_hit and relative_hit, "policy"


def _triage(triage: object, path: str) -> tuple[str, str | None, dict[str, str] | None]:
    entry = _require_object(triage, path)
    values: list[str] = []
    for stage in STAGE_ORDER:
        if stage not in entry:
            raise ValueError(f"{path}.{stage} is required")
        values.append(_require_enum(entry.get(stage), f"{path}.{stage}", STAGE_VALUES))
    unexpected = set(entry) - set(STAGE_ORDER)
    if unexpected:
        raise ValueError(f"{path} contains unknown stages: {', '.join(sorted(unexpected))}")

    blocking_index = next(
        (index for index, value in enumerate(values) if value in BLOCKING_VALUES), None
    )
    explains_index = next((index for index, value in enumerate(values) if value == "explains"), None)
    blocking_stage = STAGE_ORDER[blocking_index] if blocking_index is not None else None

    if all(value == "not_checked" for value in values):
        return "not_triaged", blocking_stage, None
    if explains_index is None:
        return "unresolved", blocking_stage, None
    if blocking_index is None or blocking_index > explains_index:
        return STAGE_ORDER[explains_index], blocking_stage, None
    return (
        "premature",
        blocking_stage,
        {"claimed_stage": STAGE_ORDER[explains_index], "blocking_stage": blocking_stage},
    )


def _parse_lines(
    payload: dict[str, Any],
    *,
    policy: dict[str, Any] | None,
    missing: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    raw_lines = _require_list(payload.get("lines"), "lines")
    if not raw_lines:
        raise ValueError("lines must be a nonempty list")
    seen_ids: set[str] = set()
    lines: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []

    for index, raw_line in enumerate(raw_lines):
        path = f"lines[{index}]"
        line = _require_object(raw_line, path)
        line_id = _require_nonempty_string(line.get("id"), f"{path}.id")
        if line_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier line")
        seen_ids.add(line_id)
        label = _require_nonempty_string(line.get("label"), f"{path}.label")
        section = _require_enum(
            line.get("statement_section"), f"{path}.statement_section", STATEMENT_SECTIONS
        )
        direction = _require_enum(
            line.get("direction_favorable"), f"{path}.direction_favorable", FAVORABLE_DIRECTIONS
        )
        budget = _money(line.get("budget"), f"{path}.budget", allow_negative=True)
        actual = _money(line.get("actual"), f"{path}.actual", allow_negative=True)
        if budget is None:
            missing.append(f"{path}.budget")
        if actual is None:
            missing.append(f"{path}.actual")
        line_threshold = None
        if "materiality_threshold" in line:
            line_threshold = _money(
                line.get("materiality_threshold"), f"{path}.materiality_threshold"
            )
            if line_threshold is None:
                missing.append(f"{path}.materiality_threshold")
        elif policy is None:
            raise ValueError(
                "materiality must be defined by materiality_policy or by every line;"
                f" {path} has neither"
            )

        variance = None if budget is None or actual is None else actual - budget
        variance_percent = None
        percent_reason = None
        if variance is None:
            percent_reason = "unknown_amount"
        elif budget == 0:
            percent_reason = "zero_budget"
        else:
            variance_percent = _percent(variance, abs(budget))
        favorable = None
        if variance is not None and variance != 0:
            favorable = variance > 0 if direction == "higher" else variance < 0
        material, materiality_source = _materiality(
            variance=variance,
            budget=budget,
            variance_percent=variance_percent,
            line_threshold=line_threshold,
            policy=policy,
        )

        attribution, blocking_stage, violation = _triage(line.get("triage"), f"{path}.triage")
        explanation_evidence = _require_enum(
            line.get("explanation_evidence"), f"{path}.explanation_evidence", EVIDENCE_STATES
        )
        if "explanation" in line and line.get("explanation") is not None:
            _require_nonempty_string(line.get("explanation"), f"{path}.explanation")
        if not material:
            attribution, violation = "not_triaged", None
        elif attribution in STAGE_ORDER and explanation_evidence == "unknown":
            missing.append(f"{path}.explanation_evidence")
        if violation is not None:
            violations.append({"line_id": line_id, **violation})

        lines.append(
            {
                "id": line_id,
                "label": label,
                "statement_section": section,
                "direction_favorable": direction,
                "budget": budget,
                "actual": actual,
                "variance": variance,
                "variance_percent": variance_percent,
                "variance_percent_reason": percent_reason,
                "favorable": favorable,
                "material": material,
                "materiality_source": materiality_source,
                "attribution": attribution,
                "blocking_stage": blocking_stage,
                "explanation_evidence": explanation_evidence,
                "decomposition": None,
            }
        )
    return lines, violations


def _decompose(
    payload: dict[str, Any], lines: list[dict[str, Any]]
) -> None:
    by_id = {line["id"]: line for line in lines}
    seen_ids: set[str] = set()
    for index, raw_entry in enumerate(
        _require_list(payload.get("volume_price_lines", []), "volume_price_lines")
    ):
        path = f"volume_price_lines[{index}]"
        entry = _require_object(raw_entry, path)
        line_id = _require_nonempty_string(entry.get("id"), f"{path}.id")
        if line_id not in by_id:
            raise ValueError(f"{path}.id must reference a line in lines")
        if line_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier decomposition")
        seen_ids.add(line_id)
        segments = _require_list(entry.get("segments"), f"{path}.segments")
        if not segments:
            raise ValueError(f"{path}.segments must be a nonempty list")

        segment_ids: set[str] = set()
        budget_units = Decimal(0)
        actual_units = Decimal(0)
        budget_total = Decimal(0)
        actual_total = Decimal(0)
        price_effect = Decimal(0)
        for segment_index, raw_segment in enumerate(segments):
            segment_path = f"{path}.segments[{segment_index}]"
            segment = _require_object(raw_segment, segment_path)
            segment_id = _require_nonempty_string(segment.get("id"), f"{segment_path}.id")
            if segment_id in segment_ids:
                raise ValueError(f"{segment_path}.id duplicates an earlier segment")
            segment_ids.add(segment_id)
            budget_quantity = _scalar(segment.get("budget_units"), f"{segment_path}.budget_units")
            actual_quantity = _scalar(segment.get("actual_units"), f"{segment_path}.actual_units")
            budget_price = _money(segment.get("budget_unit_price"), f"{segment_path}.budget_unit_price")
            actual_price = _money(segment.get("actual_unit_price"), f"{segment_path}.actual_unit_price")
            if None in (budget_quantity, actual_quantity, budget_price, actual_price):
                raise ValueError(f"{segment_path} requires known units and unit prices")
            budget_units += budget_quantity
            actual_units += actual_quantity
            budget_total += budget_quantity * budget_price
            actual_total += actual_quantity * actual_price
            price_effect += actual_quantity * (actual_price - budget_price)

        line = by_id[line_id]
        line_budget, line_actual = line["budget"], line["actual"]
        if line_budget is not None and budget_total > abs(line_budget):
            raise ValueError(f"{path} segment budget total cannot exceed the line budget")
        total_variance = actual_total - budget_total
        budget_delta = None if line_budget is None else abs(line_budget) - budget_total
        actual_delta = None if line_actual is None else abs(line_actual) - actual_total
        partial = any(delta not in (None, 0) for delta in (budget_delta, actual_delta))
        coverage = {
            "segment_coverage_delta": budget_delta,
            "segment_actual_coverage_delta": actual_delta,
            "partial_coverage": partial,
            "mix_method": "derived_residual",
            "total_variance": total_variance,
        }
        if budget_units == 0:
            line["decomposition"] = {
                **coverage,
                "price_effect": None,
                "volume_effect": None,
                "mix_effect": None,
                "reason": "zero_budget_units",
            }
            continue
        average_price = budget_total / budget_units
        volume_effect = (actual_units - budget_units) * average_price
        line["decomposition"] = {
            **coverage,
            "price_effect": price_effect,
            "volume_effect": volume_effect,
            "mix_effect": total_variance - volume_effect - price_effect,
            "reason": None,
        }


def _totals(lines: list[dict[str, Any]]) -> dict[str, Any]:
    by_section: dict[str, dict[str, Decimal]] = {}
    for line in lines:
        if line["variance"] is None:
            continue
        section = by_section.setdefault(
            line["statement_section"],
            {"budget": Decimal(0), "actual": Decimal(0), "variance": Decimal(0)},
        )
        section["budget"] += line["budget"]
        section["actual"] += line["actual"]
        section["variance"] += line["variance"]

    gross_profit = None
    if "revenue" in by_section and "cogs" in by_section:
        revenue, cogs = by_section["revenue"], by_section["cogs"]
        gross_profit = {
            "budget": revenue["budget"] - cogs["budget"],
            "actual": revenue["actual"] - cogs["actual"],
            "variance": revenue["variance"] - cogs["variance"],
        }
    net_profit_variance = sum(
        (
            section["variance"] if name == "revenue" else -section["variance"]
            for name, section in by_section.items()
        ),
        Decimal(0),
    )

    material_lines = [line for line in lines if line["material"] is True]
    explained = sum(
        (abs(line["variance"]) for line in material_lines if line["attribution"] in STAGE_ORDER),
        Decimal(0),
    )
    unexplained = sum(
        (abs(line["variance"]) for line in material_lines if line["attribution"] not in STAGE_ORDER),
        Decimal(0),
    )
    return {
        "by_section": {name: by_section[name] for name in sorted(by_section)},
        "gross_profit": gross_profit,
        "net_profit_variance": net_profit_variance,
        "material_line_count": len(material_lines),
        "explained_material_variance_amount": explained,
        "unexplained_material_variance_amount": unexplained,
    }


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    as_of = _parse_date(payload.get("as_of_date"), "as_of_date")
    currency = payload.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.match(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    period = _require_object(payload.get("period"), "period")
    period_label = _require_nonempty_string(period.get("label"), "period.label")
    start = _parse_date(period.get("start"), "period.start")
    end = _parse_date(period.get("end"), "period.end")
    if end < start:
        raise ValueError("period.end must not precede period.start")
    if end > as_of:
        raise ValueError("period.end must not be after as_of_date")
    close_state = _require_enum(period.get("close_state"), "period.close_state", CLOSE_STATES)
    comparison_basis = _require_enum(
        payload.get("comparison_basis"), "comparison_basis", COMPARISON_BASES
    )

    policy = _parse_materiality_policy(payload, missing)
    if policy is not None:
        if policy["absolute"] is not None and policy["absolute"] < 0:
            raise ValueError("materiality_policy.absolute.amount must be nonnegative")
        if policy["relative_percent"] is not None and policy["relative_percent"] < 0:
            raise ValueError("materiality_policy.relative_percent.value must be nonnegative")

    lines, violations = _parse_lines(payload, policy=policy, missing=missing)
    _decompose(payload, lines)

    line_ids = {line["id"] for line in lines}
    candidates = []
    for index, candidate in enumerate(
        _require_list(payload.get("structural_candidates", []), "structural_candidates")
    ):
        candidate_id = _require_nonempty_string(candidate, f"structural_candidates[{index}]")
        if candidate_id not in line_ids:
            raise ValueError(f"structural_candidates[{index}] must reference a line in lines")
        candidates.append(candidate_id)

    totals = _totals(lines)
    structural_findings = [
        {
            "line_id": line["id"],
            "variance": line["variance"],
            "attribution": line["attribution"],
            "statement_section": line["statement_section"],
        }
        for line in lines
        if line["attribution"] == "real_change" and line["id"] in candidates
    ]

    indeterminate = any(line["variance"] is None for line in lines) or (
        policy is not None
        and (policy["absolute"] is None or policy["relative_percent"] is None)
    )
    if indeterminate:
        review_status = "indeterminate"
    elif totals["unexplained_material_variance_amount"] > totals["explained_material_variance_amount"]:
        review_status = "unexplained"
    elif totals["unexplained_material_variance_amount"] > 0:
        review_status = "partially_explained"
    else:
        review_status = "explained"

    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "period": {
            "label": period_label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "close_state": close_state,
        },
        "comparison_basis": comparison_basis,
        "provisional": close_state == "preliminary",
        "lines": lines,
        "triage_violations": violations,
        "totals": totals,
        "structural_findings": structural_findings,
        "review_status": review_status,
        "missing_inputs": missing,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_budget_variance.py <input.json>", file=sys.stderr)
        return 2
    try:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
        payload = json.loads(raw, parse_float=Decimal)
        result = calculate(_require_object(payload, "input"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
