#!/usr/bin/env python3
"""Deterministic scoring engine for Japanese bank-loan readiness."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

MODE_CONFIG = {
    "startup": {
        "weights": {
            "business_plan": 25,
            "funding_plan": 20,
            "repayment_capacity": 20,
            "founder_capability": 15,
            "compliance": 15,
            "documentation": 5,
        },
        "core": {"funding_plan", "repayment_capacity", "compliance"},
    },
    "operating_company": {
        "weights": {
            "repayment_capacity": 30,
            "financial_health": 20,
            "business_viability": 15,
            "borrowing_suitability": 15,
            "compliance": 15,
            "documentation": 5,
        },
        "core": {
            "repayment_capacity",
            "financial_health",
            "borrowing_suitability",
            "compliance",
        },
    },
}

EVIDENCE_FACTORS = {"confirmed": 1.0, "reported": 0.6, "inferred": 0.3, "unknown": 0.0}
CAPS = {"major": 59, "critical": 39}


def readiness_band(score: float) -> str:
    if score >= 80:
        return "ready"
    if score >= 65:
        return "conditionally_ready"
    if score >= 50:
        return "improvement_priority"
    return "significant_issues"


def _validate(payload: dict[str, object]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    mode = payload.get("mode")
    if mode not in MODE_CONFIG:
        raise ValueError("mode must be a known mode")
    criteria = payload.get("criteria")
    if not isinstance(criteria, dict):
        raise ValueError("criteria must be an object")
    config = MODE_CONFIG[mode]
    weights = config["weights"]
    if set(criteria) != set(weights):
        raise ValueError("criteria must contain exactly the expected keys")
    for name, entry in criteria.items():
        if not isinstance(entry, dict):
            raise ValueError(f"criterion {name} must be an object")
        rating = entry.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not 0 <= rating <= 5:
            raise ValueError(f"criterion {name} rating must be a number from 0 through 5")
        evidence = entry.get("evidence")
        if evidence not in EVIDENCE_FACTORS:
            raise ValueError(f"criterion {name} evidence must be known")
    flags = payload.get("red_flags", [])
    if not isinstance(flags, list):
        raise ValueError("red_flags must be a list")
    for index, flag in enumerate(flags):
        if not isinstance(flag, dict):
            raise ValueError(f"red flag {index} must be an object")
        severity = flag.get("severity")
        if severity not in CAPS:
            raise ValueError(f"red flag {index} severity must be known")
        evidence = flag.get("evidence")
        if evidence not in {"confirmed", "reported"}:
            raise ValueError(f"red flag evidence must be confirmed or reported (red flag {index})")
    return config, criteria, flags


def calculate(payload: dict[str, object]) -> dict[str, object]:
    config, criteria, flags = _validate(payload)
    weights = config["weights"]
    criterion_points = {
        name: round(weight * float(entry["rating"]) / 5, 2)
        for name, (weight, entry) in ((name, (weights[name], criteria[name])) for name in weights)
    }
    raw_score = round(sum(criterion_points.values()), 2)
    confidence_percent = round(
        sum(weights[name] * EVIDENCE_FACTORS[criteria[name]["evidence"]] for name in weights), 2
    )
    missing = sorted(name for name in config["core"] if criteria[name]["evidence"] == "unknown")
    provisional = confidence_percent < 60 or bool(missing)
    applied_cap = min((CAPS[flag["severity"]] for flag in flags), default=None)
    final_score = round(min(raw_score, applied_cap) if applied_cap is not None else raw_score, 2)
    return {
        "mode": payload["mode"],
        "raw_score": raw_score,
        "final_score": final_score,
        "confidence_percent": confidence_percent,
        "provisional": provisional,
        "readiness_band": readiness_band(final_score),
        "criterion_points": criterion_points,
        "missing_core_criteria": missing,
        "applied_cap": applied_cap,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file path, or - for standard input")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = handle.read()
        payload = json.loads(raw)
        result = calculate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
