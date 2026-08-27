#!/usr/bin/env python3
"""Score a grant application package and back-schedule its remaining gaps."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

DRAFT_ORDINAL = {"not_started": 0, "outline": 1, "draft": 2, "reviewed": 3, "final": 4}
EVIDENCE_FACTORS = {
    "documented": Decimal("1.0"),
    "reported": Decimal("0.6"),
    "estimated": Decimal("0.3"),
    "unknown": Decimal("0"),
}
REQUIREMENT_TYPES = {"required", "conditional", "optional"}
FIT_STATUSES = {"confirmed", "likely", "unclear", "ineligible", "not_applicable"}
FIT_DECISIONS_ALLOWED = {"進める", "追加確認"}
FIT_DECISIONS = FIT_DECISIONS_ALLOWED | {"見送る"}
DEADLINE_EVIDENCE = {"official_current", "official_historical", "reported", "unknown"}
PREPARATION_KINDS = {"document", "account", "review", "certification"}
PREPARATION_STATUSES = {
    "held",
    "requested",
    "in_progress",
    "not_started",
    "not_applicable",
    "unknown",
}
ISSUERS = {"external_authority", "external_vendor", "expert", "internal"}
SCALAR_EVIDENCE = {"official_current", "official_historical", "reported", "estimated", "unknown"}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
PERCENT_UNIT = Decimal("0.1")


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


def _require_boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
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


def _number(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{path} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must be finite")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{path} must be finite")
    return number


def _scalar(value: object, path: str) -> Decimal | None:
    entry = _require_object(value, path)
    evidence = _require_enum(entry.get("evidence"), f"{path}.evidence", SCALAR_EVIDENCE)
    raw = entry.get("value")
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown value must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.value is required when evidence is known")
    return _number(raw, f"{path}.value")


def _source(value: object, path: str, *, as_of: date) -> dict[str, str]:
    entry = _require_object(value, path)
    checked_on = _parse_date(entry.get("checked_on"), f"{path}.checked_on")
    if checked_on > as_of:
        raise ValueError(f"{path}.checked_on must not be after as_of_date")
    return {
        "authority": _require_nonempty_string(entry.get("authority"), f"{path}.authority"),
        "document": _require_nonempty_string(entry.get("document"), f"{path}.document"),
        "url": _require_nonempty_string(entry.get("url"), f"{path}.url"),
        "checked_on": checked_on.isoformat(),
        "version": _require_nonempty_string(entry.get("version"), f"{path}.version"),
    }


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _score_sections(
    payload: dict[str, Any], *, identifiers: set[str], missing: list[str]
) -> dict[str, Any]:
    raw_sections = _require_list(payload.get("sections"), "sections")
    if not raw_sections:
        raise ValueError("sections must be a nonempty list")
    scored: list[dict[str, Any]] = []
    unsupported_final: list[str] = []
    not_started_required: list[str] = []
    total_hours = Decimal(0)
    hours_known = True

    for index, raw_section in enumerate(raw_sections):
        path = f"sections[{index}]"
        section = _require_object(raw_section, path)
        section_id = _require_nonempty_string(section.get("id"), f"{path}.id")
        if section_id in identifiers:
            raise ValueError(f"{path}.id duplicates an earlier identifier")
        identifiers.add(section_id)
        _require_nonempty_string(section.get("label"), f"{path}.label")
        requirement_type = _require_enum(
            section.get("requirement_type"), f"{path}.requirement_type", REQUIREMENT_TYPES
        )
        weight = _scalar(section.get("weight"), f"{path}.weight")
        if weight is None:
            raise ValueError(f"{path}.weight must be known to score a section")
        if weight <= 0:
            raise ValueError(f"{path}.weight.value must be positive")
        draft_state = _require_enum(section.get("draft_state"), f"{path}.draft_state", set(DRAFT_ORDINAL))
        evidence_backing = _require_enum(
            section.get("evidence_backing"), f"{path}.evidence_backing", set(EVIDENCE_FACTORS)
        )
        _require_nonempty_string(
            section.get("official_criterion_reference"), f"{path}.official_criterion_reference"
        )
        _require_nonempty_string(section.get("owner"), f"{path}.owner")
        hours = _scalar(section.get("estimated_hours"), f"{path}.estimated_hours")
        if hours is None:
            missing.append(f"{path}.estimated_hours")
            hours_known = False
        elif hours < 0:
            raise ValueError(f"{path}.estimated_hours.value must be nonnegative")
        else:
            total_hours += hours

        ordinal = DRAFT_ORDINAL[draft_state]
        points = Decimal(0) if evidence_backing == "unknown" else weight * Decimal(ordinal) / Decimal(4)
        if evidence_backing == "unknown":
            missing.append(f"{path}.evidence_backing")
            if draft_state in {"reviewed", "final"}:
                unsupported_final.append(section_id)
        if requirement_type == "required" and draft_state == "not_started":
            not_started_required.append(section_id)
        scored.append(
            {
                "id": section_id,
                "requirement_type": requirement_type,
                "weight": weight,
                "draft_ordinal": ordinal,
                "points": points,
                "max_points": weight,
                "evidence_backing": evidence_backing,
            }
        )

    def _percent(items: list[dict[str, Any]]) -> Decimal | None:
        total_weight = sum((item["weight"] for item in items), Decimal(0))
        if total_weight == 0:
            return None
        earned = sum((item["points"] for item in items), Decimal(0))
        return (earned / total_weight * Decimal(100)).quantize(PERCENT_UNIT)

    required = [item for item in scored if item["requirement_type"] == "required"]
    total_weight = sum((item["weight"] for item in scored), Decimal(0))
    confidence = (
        sum(
            (item["weight"] * EVIDENCE_FACTORS[item["evidence_backing"]] for item in scored),
            Decimal(0),
        )
        / total_weight
        * Decimal(100)
    ).quantize(PERCENT_UNIT)
    return {
        "scored": scored,
        "required_readiness_percent": _percent(required),
        "all_sections_readiness_percent": _percent(scored),
        "confidence_percent": confidence,
        "unsupported_final_sections": unsupported_final,
        "not_started_required_sections": not_started_required,
        "estimated_hours": total_hours,
        "hours_known": hours_known,
    }


def _score_items(
    payload: dict[str, Any], *, identifiers: set[str], missing: list[str]
) -> dict[str, Any]:
    buckets = {
        "confirmed": Decimal(0),
        "likely": Decimal(0),
        "unclear": Decimal(0),
        "ineligible": Decimal(0),
        "not_applicable": Decimal(0),
    }
    unaccepted: list[dict[str, str]] = []
    missing_certification: list[str] = []
    certification_references: list[tuple[str, str, str]] = []
    total_available = Decimal(0)

    for index, raw_item in enumerate(_require_list(payload.get("scoring_items", []), "scoring_items")):
        path = f"scoring_items[{index}]"
        item = _require_object(raw_item, path)
        item_id = _require_nonempty_string(item.get("id"), f"{path}.id")
        if item_id in identifiers:
            raise ValueError(f"{path}.id duplicates an earlier identifier")
        identifiers.add(item_id)
        _require_nonempty_string(item.get("label"), f"{path}.label")
        points = _scalar(item.get("points"), f"{path}.points")
        if points is None:
            missing.append(f"{path}.points")
            points = Decimal(0)
        elif points < 0:
            raise ValueError(f"{path}.points.value must be nonnegative")
        status = _require_enum(item.get("status"), f"{path}.status", FIT_STATUSES)
        requires_certification = _require_boolean(
            item.get("requires_certification"), f"{path}.requires_certification"
        )
        certification_id = item.get("certification_item_id")
        if requires_certification:
            if certification_id is None:
                missing_certification.append(item_id)
            else:
                certification_references.append(
                    (item_id, _require_nonempty_string(certification_id, f"{path}.certification_item_id"), path)
                )
        elif certification_id is not None:
            raise ValueError(
                f"{path}.certification_item_id is only allowed when requires_certification is true"
            )
        obligation = item.get("post_award_obligation")
        accepted = item.get("obligation_accepted")
        if accepted is not None:
            _require_boolean(accepted, f"{path}.obligation_accepted")
        if obligation is not None:
            _require_nonempty_string(obligation, f"{path}.post_award_obligation")
            if accepted is not True and status in {"confirmed", "likely"}:
                unaccepted.append({"id": item_id, "post_award_obligation": obligation})

        buckets[status] += points
        if status != "not_applicable":
            total_available += points

    return {
        "claimable_points": buckets["confirmed"],
        "contingent_points": buckets["likely"],
        "unresolved_points": buckets["unclear"],
        "forgone_points": buckets["ineligible"],
        "total_available_points": total_available,
        "items_with_unaccepted_obligations": unaccepted,
        "items_missing_certification_item": missing_certification,
        "certification_references": certification_references,
    }


def _parse_preparation(
    payload: dict[str, Any],
    *,
    identifiers: set[str],
    as_of: date,
    deadline: date,
    missing: list[str],
) -> dict[str, Any]:
    raw_items = _require_list(payload.get("preparation_items", []), "preparation_items")
    items: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    kinds: dict[str, str] = {}
    total_hours = Decimal(0)
    hours_known = True

    for index, raw_item in enumerate(raw_items):
        path = f"preparation_items[{index}]"
        item = _require_object(raw_item, path)
        item_id = _require_nonempty_string(item.get("id"), f"{path}.id")
        if item_id in identifiers:
            raise ValueError(f"{path}.id duplicates an earlier identifier")
        identifiers.add(item_id)
        _require_nonempty_string(item.get("label"), f"{path}.label")
        kind = _require_enum(item.get("kind"), f"{path}.kind", PREPARATION_KINDS)
        necessity = _require_enum(item.get("necessity"), f"{path}.necessity", REQUIREMENT_TYPES)
        status = _require_enum(item.get("status"), f"{path}.status", PREPARATION_STATUSES)
        if necessity == "required" and status == "not_applicable":
            raise ValueError(f"{path} a required preparation item cannot be not_applicable")
        _require_enum(item.get("issuer"), f"{path}.issuer", ISSUERS)
        lead_time = _scalar(item.get("lead_time_days"), f"{path}.lead_time_days")
        if lead_time is None:
            missing.append(f"{path}.lead_time_days")
        elif lead_time < 0:
            raise ValueError(f"{path}.lead_time_days.value must be nonnegative")
        elif lead_time != lead_time.to_integral_value():
            raise ValueError(f"{path}.lead_time_days.value must be a whole number of days")
        expires_on = None
        if item.get("expires_on") is not None:
            expires_on = _parse_date(item.get("expires_on"), f"{path}.expires_on")
        hours = _scalar(item.get("estimated_hours"), f"{path}.estimated_hours")
        if hours is None:
            missing.append(f"{path}.estimated_hours")
            hours_known = False
        elif hours < 0:
            raise ValueError(f"{path}.estimated_hours.value must be nonnegative")
        else:
            total_hours += hours
        if status == "unknown":
            missing.append(f"{path}.status")

        depends_on = [
            _require_nonempty_string(value, f"{path}.depends_on[{position}]")
            for position, value in enumerate(_require_list(item.get("depends_on", []), f"{path}.depends_on"))
        ]
        kinds[item_id] = kind
        order.append(item_id)
        items[item_id] = {
            "id": item_id,
            "kind": kind,
            "necessity": necessity,
            "status": status,
            "lead_time_days": lead_time,
            "expires_on": expires_on,
            "depends_on": depends_on,
            "path": path,
        }

    for item in items.values():
        for dependency in item["depends_on"]:
            if dependency not in items:
                raise ValueError(f"{item['path']}.depends_on references an unknown preparation item")
    return {"items": items, "order": order, "kinds": kinds, "hours": total_hours, "hours_known": hours_known}


def _back_schedule(preparation: dict[str, Any], *, as_of: date, deadline: date) -> dict[str, Any]:
    items = preparation["items"]
    dependents: dict[str, list[str]] = {item_id: [] for item_id in items}
    for item_id, item in items.items():
        for dependency in item["depends_on"]:
            dependents[dependency].append(item_id)

    def effective_lead(item_id: str) -> int:
        item = items[item_id]
        if item["status"] == "held":
            return 0
        return int(item["lead_time_days"]) if item["lead_time_days"] is not None else 0

    memo: dict[str, int] = {}
    successor: dict[str, str | None] = {}
    visiting: list[str] = []

    def downstream(item_id: str) -> int:
        if item_id in memo:
            return memo[item_id]
        if item_id in visiting:
            cycle = visiting[visiting.index(item_id):] + [item_id]
            raise ValueError(
                "preparation_items dependency cycle detected: " + " -> ".join(cycle)
            )
        visiting.append(item_id)
        best = 0
        best_child: str | None = None
        for child in dependents[item_id]:
            candidate = effective_lead(child) + downstream(child)
            if candidate > best:
                best, best_child = candidate, child
        visiting.pop()
        memo[item_id] = best
        successor[item_id] = best_child
        return best

    scheduled: list[dict[str, Any]] = []
    minimum_slack: int | None = None
    critical_root: str | None = None
    late_items: list[str] = []
    for item_id in preparation["order"]:
        lead = effective_lead(item_id)
        downstream_days = downstream(item_id)
        finish_by = deadline - timedelta(days=downstream_days)
        latest_start = finish_by - timedelta(days=lead)
        slack = (latest_start - as_of).days
        late = slack < 0
        if late:
            late_items.append(item_id)
        if minimum_slack is None or slack < minimum_slack:
            minimum_slack, critical_root = slack, item_id
        scheduled.append(
            {
                "id": item_id,
                "lead_time_days": items[item_id]["lead_time_days"],
                "effective_lead_days": lead,
                "downstream_lead_days": downstream_days,
                "finish_by": finish_by.isoformat(),
                "latest_start_date": latest_start.isoformat(),
                "slack_days": slack,
                "late": late,
            }
        )

    critical_path: list[str] = []
    node = critical_root
    while node is not None:
        critical_path.append(node)
        node = successor.get(node)
    return {
        "items": scheduled,
        "critical_path": critical_path,
        "minimum_slack_days": minimum_slack,
        "late_items": late_items,
    }


def _preparation_summary(
    preparation: dict[str, Any], *, deadline: date
) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {}
    blocking: list[dict[str, str]] = []
    expiring: list[str] = []
    for item_id in preparation["order"]:
        item = preparation["items"][item_id]
        bucket = counts.setdefault(item["necessity"], {})
        bucket[item["status"]] = bucket.get(item["status"], 0) + 1
        if item["expires_on"] is not None and item["expires_on"] < deadline:
            expiring.append(item_id)
            blocking.append(
                {
                    "id": item_id,
                    "necessity": item["necessity"],
                    "reason": "expiring_before_submission",
                }
            )
            continue
        if item["necessity"] == "optional":
            continue
        if item["status"] == "unknown":
            blocking.append(
                {"id": item_id, "necessity": item["necessity"], "reason": "unknown_status"}
            )
        elif item["status"] == "not_started":
            blocking.append(
                {"id": item_id, "necessity": item["necessity"], "reason": "not_started"}
            )
    return {
        "counts_by_necessity_and_status": {
            necessity: dict(sorted(counts[necessity].items())) for necessity in sorted(counts)
        },
        "blocking_items": blocking,
        "expiring_before_submission": expiring,
    }


def _build_gaps(
    *,
    sections: dict[str, Any],
    scoring: dict[str, Any],
    preparation_summary: dict[str, Any],
    schedule: dict[str, Any],
    preparation: dict[str, Any],
) -> list[dict[str, Any]]:
    latest_start = {row["id"]: row["latest_start_date"] for row in schedule["items"]}
    gaps: list[dict[str, Any]] = []
    for section_id in sections["not_started_required_sections"]:
        gaps.append(
            {
                "id": section_id,
                "area": "section",
                "severity": "high",
                "reason": "required_section_not_started",
                "latest_start_date": None,
            }
        )
    for section_id in sections["unsupported_final_sections"]:
        gaps.append(
            {
                "id": section_id,
                "area": "section",
                "severity": "high",
                "reason": "polished_without_evidence",
                "latest_start_date": None,
            }
        )
    for item in scoring["items_with_unaccepted_obligations"]:
        gaps.append(
            {
                "id": item["id"],
                "area": "scoring",
                "severity": "high",
                "reason": "post_award_obligation_not_accepted",
                "latest_start_date": None,
            }
        )
    for item_id in scoring["items_missing_certification_item"]:
        gaps.append(
            {
                "id": item_id,
                "area": "scoring",
                "severity": "medium",
                "reason": "certification_item_not_identified",
                "latest_start_date": None,
            }
        )
    for entry in preparation_summary["blocking_items"]:
        necessity = preparation["items"][entry["id"]]["necessity"]
        gaps.append(
            {
                "id": entry["id"],
                "area": "preparation",
                "severity": "high" if necessity == "required" else "medium",
                "reason": entry["reason"],
                "latest_start_date": latest_start.get(entry["id"]),
            }
        )
    for item_id in schedule["late_items"]:
        necessity = preparation["items"][item_id]["necessity"]
        gaps.append(
            {
                "id": item_id,
                "area": "preparation",
                "severity": "high" if necessity == "required" else "medium",
                "reason": "latest_start_date_passed",
                "latest_start_date": latest_start.get(item_id),
            }
        )
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(gaps, key=lambda gap: (severity_rank[gap["severity"]], gap["area"], gap["id"]))


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    status_reasons: list[str] = []
    as_of = _parse_date(payload.get("as_of_date"), "as_of_date")

    program = _require_object(payload.get("program"), "program")
    program_label = _require_nonempty_string(program.get("label"), "program.label")
    round_label = _require_nonempty_string(program.get("round_label"), "program.round_label")
    _source(program.get("requirements_source"), "program.requirements_source", as_of=as_of)

    fit = _require_object(payload.get("fit_assessment"), "fit_assessment")
    decision = _require_enum(fit.get("decision"), "fit_assessment.decision", FIT_DECISIONS)
    gate_requirements: list[dict[str, str]] = []
    for index, raw_requirement in enumerate(
        _require_list(fit.get("gate_requirements"), "fit_assessment.gate_requirements")
    ):
        path = f"fit_assessment.gate_requirements[{index}]"
        requirement = _require_object(raw_requirement, path)
        gate_requirements.append(
            {
                "id": _require_nonempty_string(requirement.get("id"), f"{path}.id"),
                "status": _require_enum(requirement.get("status"), f"{path}.status", FIT_STATUSES),
            }
        )
    ineligible_gates = [item["id"] for item in gate_requirements if item["status"] == "ineligible"]
    unclear_gates = [item["id"] for item in gate_requirements if item["status"] == "unclear"]

    deadline_block = _require_object(payload.get("submission_deadline"), "submission_deadline")
    deadline_evidence = _require_enum(
        deadline_block.get("evidence"), "submission_deadline.evidence", DEADLINE_EVIDENCE
    )
    deadline = _parse_date(deadline_block.get("date"), "submission_deadline.date")
    if deadline < as_of:
        raise ValueError("submission_deadline.date must not precede as_of_date")
    deadline_time = deadline_block.get("time")
    if not isinstance(deadline_time, str) or not TIME_PATTERN.match(deadline_time):
        raise ValueError("submission_deadline.time must be an HH:MM time")
    if deadline_evidence == "unknown":
        missing.append("submission_deadline.evidence")
    days_to_deadline = (deadline - as_of).days

    identifiers: set[str] = set()
    sections = _score_sections(payload, identifiers=identifiers, missing=missing)
    scoring = _score_items(payload, identifiers=identifiers, missing=missing)
    preparation = _parse_preparation(
        payload, identifiers=identifiers, as_of=as_of, deadline=deadline, missing=missing
    )
    for item_id, certification_id, path in scoring.pop("certification_references"):
        target = preparation["items"].get(certification_id)
        if target is None or target["kind"] != "certification":
            raise ValueError(
                f"{path}.certification_item_id must reference a preparation item of kind certification"
            )
    schedule = _back_schedule(preparation, as_of=as_of, deadline=deadline)
    preparation_summary = _preparation_summary(preparation, deadline=deadline)

    available_per_week = _scalar(
        payload.get("available_hours_per_week"), "available_hours_per_week"
    )
    if available_per_week is None:
        missing.append("available_hours_per_week")
        status_reasons.append("available_hours_per_week is unknown; effort was not evaluated")
    elif available_per_week <= 0:
        raise ValueError("available_hours_per_week.value must be positive")
    total_hours = sections["estimated_hours"] + preparation["hours"]
    hours_known = sections["hours_known"] and preparation["hours_known"]
    weeks_to_deadline = (Decimal(days_to_deadline) / Decimal(7)).quantize(Decimal("0.01"))
    available_hours = (
        (available_per_week * weeks_to_deadline).quantize(Decimal("0.01"))
        if available_per_week is not None
        else None
    )
    hours_shortfall = (
        max(Decimal(0), total_hours - available_hours)
        if available_hours is not None and hours_known
        else None
    )
    if not hours_known:
        status_reasons.append("some estimated hours are unknown; the effort total is a lower bound")

    gaps = _build_gaps(
        sections=sections,
        scoring=scoring,
        preparation_summary=preparation_summary,
        schedule=schedule,
        preparation=preparation,
    )

    required_late = [
        item_id
        for item_id in schedule["late_items"]
        if preparation["items"][item_id]["necessity"] == "required"
    ]
    optional_late = [
        item_id for item_id in schedule["late_items"] if item_id not in required_late
    ]
    required_expiring = [
        item_id
        for item_id in preparation_summary["expiring_before_submission"]
        if preparation["items"][item_id]["necessity"] == "required"
    ]
    required_unknown = [
        entry["id"]
        for entry in preparation_summary["blocking_items"]
        if entry["reason"] == "unknown_status" and entry["necessity"] == "required"
    ]
    unknown_required_lead_time = [
        item_id
        for item_id in preparation["order"]
        if preparation["items"][item_id]["necessity"] == "required"
        and preparation["items"][item_id]["lead_time_days"] is None
    ]
    unknown_required_evidence = [
        item["id"]
        for item in sections["scored"]
        if item["requirement_type"] == "required" and item["evidence_backing"] == "unknown"
    ]

    if deadline_evidence == "unknown":
        status_reasons.append("the submission deadline is not confirmed against current official sources")
    if unclear_gates:
        status_reasons.append("gate requirements remain unclear; return to grant-subsidy-fit")

    if (
        deadline_evidence == "unknown"
        or required_unknown
        or unknown_required_lead_time
        or unknown_required_evidence
    ):
        readiness_status = "indeterminate"
    elif ineligible_gates or decision not in FIT_DECISIONS_ALLOWED or required_late or required_expiring:
        readiness_status = "blocked"
    elif (hours_shortfall is not None and hours_shortfall > 0) or optional_late:
        readiness_status = "gaps_without_time"
    elif gaps:
        readiness_status = "gaps_with_time"
    else:
        readiness_status = "submission_path_clear"

    if ineligible_gates:
        status_reasons.append(
            "a gate requirement is ineligible; this package cannot be made ready as scoped"
        )
    if decision not in FIT_DECISIONS_ALLOWED:
        status_reasons.append("the fit assessment did not conclude 進める or 追加確認")

    return {
        "as_of_date": as_of.isoformat(),
        "program_label": program_label,
        "round_label": round_label,
        "submission_deadline": {
            "date": deadline.isoformat(),
            "time": deadline_time,
            "evidence": deadline_evidence,
        },
        "days_to_deadline": days_to_deadline,
        "fit_assessment": {
            "decision": decision,
            "ineligible_gate_requirements": ineligible_gates,
            "unclear_gate_requirements": unclear_gates,
        },
        "readiness_status": readiness_status,
        "sections": {
            "scored": sections["scored"],
            "required_readiness_percent": sections["required_readiness_percent"],
            "all_sections_readiness_percent": sections["all_sections_readiness_percent"],
            "confidence_percent": sections["confidence_percent"],
            "unsupported_final_sections": sections["unsupported_final_sections"],
            "not_started_required_sections": sections["not_started_required_sections"],
        },
        "scoring": scoring,
        "preparation": preparation_summary,
        "schedule": schedule,
        "effort": {
            "total_estimated_hours": total_hours,
            "hours_known": hours_known,
            "weeks_to_deadline": weeks_to_deadline,
            "available_hours": available_hours,
            "hours_shortfall": hours_shortfall,
        },
        "gaps": gaps,
        "missing_inputs": missing,
        "status_reasons": status_reasons,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: score_application_readiness.py <input.json>", file=sys.stderr)
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
