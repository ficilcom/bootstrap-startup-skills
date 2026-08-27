#!/usr/bin/env python3
"""Deterministically summarize an aligned founder-led sales pipeline cohort."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"{field} must be a YYYY-MM-DD date") from error


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def summarize(input_data: dict[str, Any]) -> dict[str, Any]:
    as_of = parse_date(input_data.get("as_of_date"), "as_of_date")
    cohort = require_mapping(input_data.get("cohort"), "cohort")
    cohort_start = parse_date(cohort.get("start"), "cohort.start")
    cohort_end = parse_date(cohort.get("end"), "cohort.end")
    minimum_observation = cohort.get("minimum_observation_days")
    if not isinstance(minimum_observation, int) or minimum_observation < 0:
        raise ValueError("cohort.minimum_observation_days must be a non-negative integer")
    if cohort_start > cohort_end or cohort_end > as_of:
        raise ValueError("cohort dates must satisfy start <= end <= as_of_date")

    stages = require_list(input_data.get("stage_order"), "stage_order")
    if len(stages) < 2 or any(not isinstance(stage, str) or not stage for stage in stages):
        raise ValueError("stage_order must contain at least two non-empty stage names")
    if len(set(stages)) != len(stages):
        raise ValueError("stage_order contains duplicate stage names")
    stage_index = {stage: index for index, stage in enumerate(stages)}

    stale_after = require_mapping(input_data.get("stale_after_days", {}), "stale_after_days")
    for stage, days in stale_after.items():
        if stage not in stage_index or not isinstance(days, int) or days < 0:
            raise ValueError("stale_after_days must map known stages to non-negative integers")

    opportunities = require_list(input_data.get("opportunities"), "opportunities")
    by_id: dict[str, dict[str, Any]] = {}
    stage_entries: dict[str, list[tuple[str, date]]] = defaultdict(list)
    for raw_opportunity in opportunities:
        opportunity = require_mapping(raw_opportunity, "opportunities item")
        opportunity_id = opportunity.get("id")
        if not isinstance(opportunity_id, str) or not opportunity_id or opportunity_id in by_id:
            raise ValueError("each opportunity requires a unique non-empty id")
        initial_stage = opportunity.get("initial_stage")
        current_stage = opportunity.get("current_stage")
        if initial_stage not in stage_index or current_stage not in stage_index:
            raise ValueError(f"opportunity {opportunity_id} uses an unknown stage")
        created_at = parse_date(opportunity.get("created_at"), f"opportunity {opportunity_id}.created_at")
        entered_current = parse_date(
            opportunity.get("entered_current_stage_at"),
            f"opportunity {opportunity_id}.entered_current_stage_at",
        )
        if created_at > as_of or entered_current > as_of:
            raise ValueError(f"opportunity {opportunity_id} has a date after as_of_date")
        if entered_current < created_at:
            raise ValueError(f"opportunity {opportunity_id}.entered_current_stage_at cannot precede created_at")
        by_id[opportunity_id] = opportunity
        stage_entries[opportunity_id].append((initial_stage, created_at))

    transitions = require_list(input_data.get("transitions"), "transitions")
    transitions_by_id: dict[str, list[tuple[str, str, date]]] = defaultdict(list)
    for raw_transition in transitions:
        transition = require_mapping(raw_transition, "transitions item")
        opportunity_id = transition.get("opportunity_id")
        if opportunity_id not in by_id:
            raise ValueError("every transition must reference an opportunity")
        source, target = transition.get("from_stage"), transition.get("to_stage")
        if source not in stage_index or target not in stage_index:
            raise ValueError("every transition must use a stage in stage_order")
        if stage_index[target] != stage_index[source] + 1:
            raise ValueError("transitions must move to the next stage in stage_order")
        occurred_at = parse_date(transition.get("occurred_at"), "transition.occurred_at")
        if occurred_at > as_of:
            raise ValueError("transition.occurred_at cannot be after as_of_date")
        transitions_by_id[opportunity_id].append((source, target, occurred_at))

    for opportunity_id, history in transitions_by_id.items():
        expected_source = by_id[opportunity_id]["initial_stage"]
        previous_date = stage_entries[opportunity_id][0][1]
        for source, target, occurred_at in history:
            if source != expected_source or occurred_at < previous_date:
                raise ValueError(f"transitions for {opportunity_id} are out of sequence")
            stage_entries[opportunity_id].append((target, occurred_at))
            expected_source, previous_date = target, occurred_at
        if by_id[opportunity_id]["current_stage"] != expected_source:
            raise ValueError(f"opportunity {opportunity_id}.current_stage does not match transition history")
        if parse_date(by_id[opportunity_id]["entered_current_stage_at"], "entered_current_stage_at") != previous_date:
            raise ValueError(f"opportunity {opportunity_id}.entered_current_stage_at does not match history")

    stage_metrics: list[dict[str, Any]] = []
    cutoff_ordinal = as_of.toordinal() - minimum_observation
    for index, stage in enumerate(stages[:-1]):
        next_stage = stages[index + 1]
        eligible: list[tuple[str, date]] = []
        durations: list[int] = []
        converted = 0
        for opportunity_id, entries in stage_entries.items():
            for entry_index, (entry_stage, entered_at) in enumerate(entries):
                if entry_stage != stage or not (cohort_start <= entered_at <= cohort_end):
                    continue
                if entered_at.toordinal() > cutoff_ordinal:
                    continue
                eligible.append((opportunity_id, entered_at))
                if entry_index + 1 < len(entries) and entries[entry_index + 1][0] == next_stage:
                    converted += 1
                    durations.append((entries[entry_index + 1][1] - entered_at).days)
        stage_metrics.append(
            {
                "stage": stage,
                "next_stage": next_stage,
                "eligible_cohort_entries": len(eligible),
                "converted_to_next_stage": converted,
                "conversion_rate": rate(converted, len(eligible)),
                "median_days_to_next_stage": median(durations) if durations else None,
            }
        )

    losses = require_list(input_data.get("losses", []), "losses")
    cohort_ids = {
        opportunity_id
        for opportunity_id, entries in stage_entries.items()
        if any(cohort_start <= entered_at <= cohort_end for _, entered_at in entries)
    }
    loss_reasons: Counter[str] = Counter()
    unknown_loss_reasons = 0
    lost_ids: set[str] = set()
    for raw_loss in losses:
        loss = require_mapping(raw_loss, "losses item")
        opportunity_id = loss.get("opportunity_id")
        if opportunity_id not in by_id:
            raise ValueError("every loss must reference an opportunity")
        if opportunity_id in lost_ids:
            raise ValueError("an opportunity can have at most one loss")
        lost_at = parse_date(loss.get("lost_at"), "loss.lost_at")
        if lost_at > as_of:
            raise ValueError("loss.lost_at cannot be after as_of_date")
        created_at = parse_date(by_id[opportunity_id]["created_at"], "opportunity.created_at")
        if lost_at < created_at:
            raise ValueError("loss.lost_at cannot precede opportunity.created_at")
        lost_ids.add(opportunity_id)
        if opportunity_id not in cohort_ids:
            continue
        reason = loss.get("reason")
        if isinstance(reason, str) and reason.strip():
            loss_reasons[reason.strip()] += 1
        else:
            unknown_loss_reasons += 1

    open_pipeline: list[dict[str, Any]] = []
    for opportunity_id, opportunity in sorted(by_id.items()):
        current_stage = opportunity["current_stage"]
        if current_stage == stages[-1] or opportunity_id in lost_ids:
            continue
        entered_at = parse_date(opportunity["entered_current_stage_at"], "entered_current_stage_at")
        age_days = (as_of - entered_at).days
        threshold = stale_after.get(current_stage)
        open_pipeline.append(
            {
                "opportunity_id": opportunity_id,
                "current_stage": current_stage,
                "age_days": age_days,
                "stale_after_days": threshold,
                "is_stale": age_days > threshold if threshold is not None else None,
            }
        )

    return {
        "as_of_date": as_of.isoformat(),
        "cohort": {
            "start": cohort_start.isoformat(),
            "end": cohort_end.isoformat(),
            "minimum_observation_days": minimum_observation,
        },
        "stage_metrics": stage_metrics,
        "open_pipeline": open_pipeline,
        "open_pipeline_summary": {
            "count": len(open_pipeline),
            "stale_count": sum(item["is_stale"] is True for item in open_pipeline),
        },
        "loss_reasons": {
            "known": [
                {"reason": reason, "count": count}
                for reason, count in sorted(loss_reasons.items(), key=lambda item: (-item[1], item[0]))
            ],
            "unknown_count": unknown_loss_reasons,
            "total": sum(loss_reasons.values()) + unknown_loss_reasons,
        },
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_pipeline.py <input.json>", file=sys.stderr)
        return 2
    try:
        input_data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = summarize(require_mapping(input_data, "input"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
