#!/usr/bin/env python3
"""Plan post-award grant execution: eligible spend, clawback exposure, and bridge financing."""

from __future__ import annotations

import calendar
import json
import math
import re
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

OFFICIAL_EVIDENCE = {"official_current", "official_historical", "reported", "estimated", "unknown"}
MONEY_EVIDENCE = {"official_current", "official_historical", "confirmed", "reported", "estimated", "unknown"}
COST_CATEGORIES = {
    "machinery",
    "outsourcing",
    "personnel",
    "travel",
    "advertising",
    "expert_fee",
    "system",
    "other",
}
ELIGIBILITY_STATUSES = {"confirmed", "likely", "unclear", "ineligible", "not_applicable"}
PAYMENT_METHODS = {"bank_transfer", "credit_card", "cash", "other", "unknown"}
EVIDENCE_KINDS = {
    "quote",
    "order",
    "contract",
    "invoice",
    "delivery",
    "bank_transfer_record",
    "photo",
    "timesheet",
    "acceptance",
}
NECESSITIES = {"required", "conditional", "optional"}
EVIDENCE_ITEM_STATUSES = {"held", "pending", "missing", "not_applicable", "unknown"}
FINANCING_STATUSES = {"confirmed", "reported", "estimated", "unknown"}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
RISK_SEVERITY = {
    "ordered_before_approval": "high",
    "eligibility_ineligible": "high",
    "payment_after_project_period": "high",
    "eligibility_unclear": "medium",
    "quote_shortfall": "medium",
    "missing_required_evidence": "medium",
    "quotes_required_unknown": "medium",
    "cash_payment": "low",
    "pending_required_evidence": "low",
}
RISK_DETAIL = {
    "ordered_before_approval": "交付決定前に発注または着手している",
    "eligibility_ineligible": "対象外と確認済みの経費が計画に残っている",
    "payment_after_project_period": "支払予定日が事業実施期間を過ぎている",
    "eligibility_unclear": "対象・対象外が未確認である",
    "quote_shortfall": "必要な相見積の件数に達していない",
    "missing_required_evidence": "必須の証憑が欠落している",
    "quotes_required_unknown": "必要な相見積の件数を確認していない",
    "cash_payment": "現金払いのため支払の事実を証明しにくい",
    "pending_required_evidence": "必須の証憑が未入手である",
}
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
CENT = Decimal("0.01")


def month_index_of(value: date) -> int:
    return value.year * 12 + value.month - 1


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_end(index: int) -> date:
    year, month = index // 12, index % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


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


def _require_enum(value: object, path: str, allowed: set[str]) -> str:
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


def _parse_month(value: object, path: str) -> int:
    if not isinstance(value, str) or not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise ValueError(f"{path} must be a YYYY-MM month")
    year, month = value.split("-")
    return int(year) * 12 + int(month) - 1


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


def _entry(value: object, path: str, key: str, allowed: set[str], *, allow_negative: bool) -> Decimal | None:
    entry = _require_object(value, path)
    evidence = _require_enum(entry.get("evidence"), f"{path}.evidence", allowed)
    raw = entry.get(key)
    if evidence == "unknown":
        if raw is not None:
            raise ValueError(f"{path} unknown {key} must be null")
        return None
    if raw is None:
        raise ValueError(f"{path}.{key} is required when evidence is known")
    return _number(raw, f"{path}.{key}", allow_negative=allow_negative)


def _money(value: object, path: str, *, allow_negative: bool = False) -> Decimal | None:
    return _entry(value, path, "amount", MONEY_EVIDENCE, allow_negative=allow_negative)


def _scalar(value: object, path: str) -> Decimal | None:
    return _entry(value, path, "value", OFFICIAL_EVIDENCE, allow_negative=False)


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


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


def _parse_grant(payload: dict[str, Any], *, as_of: date, missing: list[str]) -> dict[str, Any]:
    path = "grant"
    grant = _require_object(payload.get(path), path)
    label = _require_nonempty_string(grant.get("label"), f"{path}.label")
    decision_date = _parse_date(grant.get("decision_date"), f"{path}.decision_date")
    approved_total = _money(
        grant.get("approved_total_eligible_cost"), f"{path}.approved_total_eligible_cost"
    )
    if approved_total is None:
        missing.append(f"{path}.approved_total_eligible_cost")
    rate = _scalar(grant.get("subsidy_rate"), f"{path}.subsidy_rate")
    if rate is None:
        missing.append(f"{path}.subsidy_rate")
    elif rate <= 0 or rate > 1:
        raise ValueError(f"{path}.subsidy_rate.value must be greater than 0 and at most 1")
    cap = _money(grant.get("subsidy_cap"), f"{path}.subsidy_cap")
    if cap is None:
        missing.append(f"{path}.subsidy_cap")
    project_start = _parse_date(grant.get("project_start_date"), f"{path}.project_start_date")
    project_end = _parse_date(grant.get("project_end_date"), f"{path}.project_end_date")
    report_due = _parse_date(grant.get("report_due_date"), f"{path}.report_due_date")
    if project_end < project_start:
        raise ValueError(f"{path}.project_end_date must not precede project_start_date")
    if report_due < project_end:
        raise ValueError(f"{path}.report_due_date must not precede project_end_date")
    interim = _require_boolean(grant.get("interim_payment_available"), f"{path}.interim_payment_available")

    payment_block = _require_object(grant.get("expected_payment_date"), f"{path}.expected_payment_date")
    payment_evidence = _require_enum(
        payment_block.get("evidence"), f"{path}.expected_payment_date.evidence", OFFICIAL_EVIDENCE
    )
    raw_payment_date = payment_block.get("date")
    payment_date: date | None = None
    if payment_evidence == "unknown":
        if raw_payment_date is not None:
            raise ValueError(f"{path}.expected_payment_date unknown date must be null")
        missing.append(f"{path}.expected_payment_date")
    else:
        if raw_payment_date is None:
            raise ValueError(f"{path}.expected_payment_date.date is required when evidence is known")
        payment_date = _parse_date(raw_payment_date, f"{path}.expected_payment_date.date")
        if payment_date < project_end and not interim:
            raise ValueError(
                f"{path}.expected_payment_date cannot precede project_end_date without an interim payment"
            )
    _source(grant.get("requirements_source"), f"{path}.requirements_source", as_of=as_of)
    return {
        "label": label,
        "decision_date": decision_date,
        "approved_total": approved_total,
        "rate": rate,
        "cap": cap,
        "project_start": project_start,
        "project_end": project_end,
        "report_due": report_due,
        "expected_payment_date": payment_date,
        "expected_payment_evidence": payment_evidence,
        "interim_payment_available": interim,
    }


def _parse_cost_items(
    payload: dict[str, Any], *, grant: dict[str, Any], missing: list[str]
) -> dict[str, Any]:
    raw_items = _require_list(payload.get("cost_items"), "cost_items")
    if not raw_items:
        raise ValueError("cost_items must be a nonempty list")
    seen_ids: set[str] = set()
    items: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    evidence_gaps: list[dict[str, str]] = []
    approved_sum = Decimal(0)
    committed_sum = Decimal(0)
    approved_known = True
    committed_known = True

    for index, raw_item in enumerate(raw_items):
        path = f"cost_items[{index}]"
        item = _require_object(raw_item, path)
        item_id = _require_nonempty_string(item.get("id"), f"{path}.id")
        if item_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier cost item")
        seen_ids.add(item_id)
        _require_nonempty_string(item.get("label"), f"{path}.label")
        category = _require_enum(item.get("category"), f"{path}.category", COST_CATEGORIES)
        approved = _money(item.get("approved_amount"), f"{path}.approved_amount")
        committed = _money(item.get("committed_amount"), f"{path}.committed_amount")
        if approved is None:
            missing.append(f"{path}.approved_amount")
            approved_known = False
        else:
            approved_sum += approved
        if committed is None:
            missing.append(f"{path}.committed_amount")
            committed_known = False
        else:
            committed_sum += committed
        payment_date = _parse_date(item.get("planned_payment_date"), f"{path}.planned_payment_date")
        eligibility = _require_enum(
            item.get("eligibility_status"), f"{path}.eligibility_status", ELIGIBILITY_STATUSES
        )
        ordered_before = _require_boolean(
            item.get("ordered_before_approval"), f"{path}.ordered_before_approval"
        )
        if payment_date < grant["decision_date"] and not ordered_before:
            raise ValueError(
                f"{path} payment precedes the decision date but is not marked ordered_before_approval"
            )
        quotes_required = _scalar(item.get("quotes_required"), f"{path}.quotes_required")
        quotes_obtained = _scalar(item.get("quotes_obtained"), f"{path}.quotes_obtained")
        if quotes_required is None:
            missing.append(f"{path}.quotes_required")
        if quotes_obtained is None:
            missing.append(f"{path}.quotes_obtained")
        paid_by = _require_enum(item.get("paid_by"), f"{path}.paid_by", PAYMENT_METHODS)
        if paid_by == "unknown":
            missing.append(f"{path}.paid_by")

        item_evidence: list[dict[str, str]] = []
        for evidence_index, raw_evidence in enumerate(
            _require_list(item.get("evidence_items", []), f"{path}.evidence_items")
        ):
            evidence_path = f"{path}.evidence_items[{evidence_index}]"
            evidence = _require_object(raw_evidence, evidence_path)
            record = {
                "kind": _require_enum(evidence.get("kind"), f"{evidence_path}.kind", EVIDENCE_KINDS),
                "necessity": _require_enum(
                    evidence.get("necessity"), f"{evidence_path}.necessity", NECESSITIES
                ),
                "status": _require_enum(
                    evidence.get("status"), f"{evidence_path}.status", EVIDENCE_ITEM_STATUSES
                ),
            }
            item_evidence.append(record)
            if record["status"] == "unknown":
                missing.append(f"{evidence_path}.status")
            if record["necessity"] == "required" and record["status"] in {"missing", "pending", "unknown"}:
                evidence_gaps.append({"item_id": item_id, **record})

        eligible = None
        if approved is not None and committed is not None:
            eligible = min(committed, approved)
        overage = (
            max(Decimal(0), committed - approved)
            if approved is not None and committed is not None
            else None
        )
        subsidy_contribution = (
            _round_money(eligible * grant["rate"])
            if eligible is not None and grant["rate"] is not None
            else None
        )
        if eligible is None:
            item_status = "indeterminate"
        elif eligibility in {"confirmed", "likely", "unclear"}:
            item_status = "counted"
        else:
            item_status = "excluded"

        at_risk = subsidy_contribution if subsidy_contribution is not None else None
        rules: list[str] = []
        if ordered_before:
            rules.append("ordered_before_approval")
        if eligibility == "ineligible":
            rules.append("eligibility_ineligible")
        if payment_date > grant["project_end"]:
            rules.append("payment_after_project_period")
        if eligibility == "unclear":
            rules.append("eligibility_unclear")
        if quotes_required is None:
            rules.append("quotes_required_unknown")
        elif quotes_obtained is not None and quotes_obtained < quotes_required:
            rules.append("quote_shortfall")
        if any(
            record["necessity"] == "required" and record["status"] == "missing"
            for record in item_evidence
        ):
            rules.append("missing_required_evidence")
        if any(
            record["necessity"] == "required" and record["status"] == "pending"
            for record in item_evidence
        ):
            rules.append("pending_required_evidence")
        if paid_by == "cash":
            rules.append("cash_payment")
        for rule in rules:
            findings.append(
                {
                    "item_id": item_id,
                    "rule": rule,
                    "severity": RISK_SEVERITY[rule],
                    "detail": RISK_DETAIL[rule],
                    "amount_at_risk": at_risk,
                }
            )

        items.append(
            {
                "id": item_id,
                "category": category,
                "approved_amount": approved,
                "committed_amount": committed,
                "eligible_amount": eligible,
                "overage": overage,
                "subsidy_contribution": subsidy_contribution,
                "eligibility_status": eligibility,
                "status": item_status,
                "planned_payment_date": payment_date.isoformat(),
                "payment_month_index": month_index_of(payment_date),
            }
        )

    if approved_known and grant["approved_total"] is not None and approved_sum > grant["approved_total"]:
        raise ValueError("cost_items approved amounts exceed grant.approved_total_eligible_cost")
    return {
        "items": items,
        "findings": findings,
        "evidence_gaps": evidence_gaps,
        "approved_sum": approved_sum if approved_known else None,
        "committed_sum": committed_sum if committed_known else None,
        "committed_known": committed_known,
    }


def _subsidy_estimate(
    items: list[dict[str, Any]], *, rate: Decimal | None, cap: Decimal | None
) -> dict[str, Any]:
    def base(statuses: set[str]) -> Decimal | None:
        total = Decimal(0)
        for item in items:
            if item["eligibility_status"] not in statuses:
                continue
            if item["eligible_amount"] is None:
                return None
            total += item["eligible_amount"]
        return total

    def subsidy(amount: Decimal | None) -> tuple[Decimal | None, bool | None]:
        if amount is None or rate is None:
            return None, None
        gross = _round_money(amount * rate)
        if cap is None:
            return gross, None
        return min(cap, gross), gross > cap

    confirmed_base = base({"confirmed"})
    likely_base = base({"confirmed", "likely"})
    unclear_base = base({"confirmed", "likely", "unclear"})
    confirmed_value, confirmed_cap = subsidy(confirmed_base)
    likely_value, likely_cap = subsidy(likely_base)
    unclear_value, unclear_cap = subsidy(unclear_base)
    overage = Decimal(0)
    overage_known = True
    for item in items:
        if item["overage"] is None:
            overage_known = False
            continue
        overage += item["overage"]
    return {
        "eligible_base_confirmed": confirmed_base,
        "eligible_base_confirmed_plus_likely": likely_base,
        "eligible_base_including_unclear": unclear_base,
        "subsidy_confirmed_only": confirmed_value,
        "subsidy_confirmed_plus_likely": likely_value,
        "subsidy_including_unclear": unclear_value,
        "cap_binding": {
            "confirmed_only": confirmed_cap,
            "confirmed_plus_likely": likely_cap,
            "including_unclear": unclear_cap,
        },
        "self_funded_overage": overage if overage_known else None,
    }


def _clawback_exposure(findings: list[dict[str, Any]]) -> dict[str, Any]:
    worst: dict[str, dict[str, Any]] = {}
    for finding in findings:
        current = worst.get(finding["item_id"])
        if current is None or SEVERITY_RANK[finding["severity"]] < SEVERITY_RANK[current["severity"]]:
            worst[finding["item_id"]] = finding
    by_severity = {"high": Decimal(0), "medium": Decimal(0), "low": Decimal(0)}
    total = Decimal(0)
    unknown_items: list[str] = []
    for item_id, finding in worst.items():
        if finding["amount_at_risk"] is None:
            unknown_items.append(item_id)
            continue
        by_severity[finding["severity"]] += finding["amount_at_risk"]
        total += finding["amount_at_risk"]
    return {
        "total_amount_at_risk": total,
        "by_severity": by_severity,
        "items_at_risk": sorted(worst),
        "items_with_unknown_exposure": sorted(unknown_items),
    }


def _cash_path(
    payload: dict[str, Any],
    *,
    as_of: date,
    grant: dict[str, Any],
    items: list[dict[str, Any]],
    subsidy_value: Decimal | None,
    missing: list[str],
) -> dict[str, Any]:
    cash = _require_object(payload.get("cash"), "cash")
    available = _money(cash.get("available_cash"), "cash.available_cash")
    buffer_amount = _money(cash.get("minimum_cash_buffer"), "cash.minimum_cash_buffer")
    if available is None:
        missing.append("cash.available_cash")
    if buffer_amount is None:
        missing.append("cash.minimum_cash_buffer")

    as_of_index = month_index_of(as_of)
    last_payment_index = max(item["payment_month_index"] for item in items)
    inflow_modeled = grant["expected_payment_evidence"] != "unknown"
    end_index = last_payment_index
    if inflow_modeled:
        end_index = max(end_index, month_index_of(grant["expected_payment_date"]))
    if end_index < as_of_index:
        end_index = as_of_index
    length = end_index - as_of_index + 1

    entries = _require_list(cash.get("monthly_net_cash_before_grant"), "cash.monthly_net_cash_before_grant")
    if len(entries) != length:
        raise ValueError(
            f"cash.monthly_net_cash_before_grant must cover through {month_label(end_index)}"
        )
    baseline: list[Decimal | None] = []
    for offset, raw_entry in enumerate(entries):
        entry_path = f"cash.monthly_net_cash_before_grant[{offset}]"
        entry = _require_object(raw_entry, entry_path)
        if _parse_month(entry.get("month"), f"{entry_path}.month") != as_of_index + offset:
            raise ValueError(f"{entry_path}.month must be {month_label(as_of_index + offset)}")
        amount = _money(entry.get("amount"), f"{entry_path}.amount", allow_negative=True)
        if amount is None:
            missing.append(f"{entry_path}.amount")
        baseline.append(amount)

    outflow_by_offset: dict[int, Decimal] = {}
    outflow_known = True
    for item in items:
        offset = item["payment_month_index"] - as_of_index
        if item["committed_amount"] is None:
            outflow_known = False
            continue
        if offset < 0:
            continue
        outflow_by_offset[offset] = outflow_by_offset.get(offset, Decimal(0)) + item["committed_amount"]

    inflow_offset = (
        month_index_of(grant["expected_payment_date"]) - as_of_index if inflow_modeled else None
    )
    determinate = (
        outflow_known
        and available is not None
        and all(amount is not None for amount in baseline)
        and (not inflow_modeled or subsidy_value is not None)
    )

    months: list[dict[str, Any]] = []
    balance = available
    lowest: dict[str, Any] | None = None
    breach_offset: int | None = None
    for offset in range(length):
        index = as_of_index + offset
        outflow = outflow_by_offset.get(offset, Decimal(0))
        inflow = subsidy_value if inflow_offset == offset and subsidy_value is not None else Decimal(0)
        closing: Decimal | None = None
        below_buffer: bool | None = None
        if determinate and balance is not None:
            closing = balance + baseline[offset] - outflow + inflow
            if buffer_amount is not None:
                below_buffer = closing < buffer_amount
                if below_buffer and breach_offset is None:
                    breach_offset = offset
            if lowest is None or closing < lowest["amount"]:
                lowest = {"month": month_label(index), "amount": closing}
        months.append(
            {
                "month": month_label(index),
                "opening": balance if determinate else None,
                "grant_outflow": outflow,
                "baseline_net": baseline[offset],
                "subsidy_inflow": inflow,
                "closing": closing,
                "below_buffer": below_buffer,
            }
        )
        if determinate:
            balance = closing

    bridge_need: Decimal | None = None
    if lowest is not None and buffer_amount is not None:
        bridge_need = max(Decimal(0), buffer_amount - lowest["amount"])
    breach_month = month_label(as_of_index + breach_offset) if breach_offset is not None else None
    breach_date = month_end(as_of_index + breach_offset).isoformat() if breach_offset is not None else None

    last_payment_date = max(item["planned_payment_date"] for item in items)
    carry_days = (
        (grant["expected_payment_date"] - date.fromisoformat(last_payment_date)).days
        if inflow_modeled
        else None
    )
    return {
        "months": months,
        "lowest_cash": lowest,
        "bridge_financing_need": bridge_need,
        "bridge_needed_from_month": breach_month,
        "bridge_needed_from_date": breach_date,
        "carry_days": carry_days,
        "subsidy_inflow_modeled": inflow_modeled,
        "determinate": determinate,
    }


def _financing(
    payload: dict[str, Any],
    *,
    need: Decimal | None,
    needed_from: str | None,
    missing: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    options: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    arrangement_dates: list[str] = []
    for index, raw_option in enumerate(
        _require_list(payload.get("financing_options", []), "financing_options")
    ):
        path = f"financing_options[{index}]"
        option = _require_object(raw_option, path)
        option_id = _require_nonempty_string(option.get("id"), f"{path}.id")
        if option_id in seen_ids:
            raise ValueError(f"{path}.id duplicates an earlier financing option")
        seen_ids.add(option_id)
        _require_nonempty_string(option.get("label"), f"{path}.label")
        _require_enum(option.get("status"), f"{path}.status", FINANCING_STATUSES)
        amount = _money(option.get("available_amount"), f"{path}.available_amount")
        lead_days = _scalar(option.get("lead_time_days"), f"{path}.lead_time_days")
        if amount is None:
            missing.append(f"{path}.available_amount")
        if lead_days is None:
            missing.append(f"{path}.lead_time_days")
        sufficient = None if amount is None or need is None else amount >= need
        shortfall = None if amount is None or need is None else max(Decimal(0), need - amount)
        arrange_by = None
        if needed_from is not None and lead_days is not None:
            arrange_by = (
                date.fromisoformat(needed_from) - timedelta(days=int(lead_days))
            ).isoformat()
        if sufficient and arrange_by is not None:
            arrangement_dates.append(arrange_by)
        options.append(
            {
                "id": option_id,
                "available_amount": amount,
                "lead_time_days": lead_days,
                "sufficient": sufficient,
                "shortfall": shortfall,
                "arrange_by_date": arrange_by,
            }
        )
    return options, min(arrangement_dates) if arrangement_dates else None


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    as_of = _parse_date(payload.get("as_of_date"), "as_of_date")
    currency = payload.get("currency")
    if not isinstance(currency, str) or not CURRENCY_PATTERN.match(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    grant = _parse_grant(payload, as_of=as_of, missing=missing)
    cost_block = _parse_cost_items(payload, grant=grant, missing=missing)
    items = cost_block["items"]
    estimate = _subsidy_estimate(items, rate=grant["rate"], cap=grant["cap"])
    estimate["approved_vs_committed_delta"] = (
        cost_block["committed_sum"] - cost_block["approved_sum"]
        if cost_block["committed_sum"] is not None and cost_block["approved_sum"] is not None
        else None
    )
    exposure = _clawback_exposure(cost_block["findings"])
    cash_path = _cash_path(
        payload,
        as_of=as_of,
        grant=grant,
        items=items,
        subsidy_value=estimate["subsidy_confirmed_plus_likely"],
        missing=missing,
    )
    options, latest_arrangement = _financing(
        payload,
        need=cash_path["bridge_financing_need"],
        needed_from=cash_path["bridge_needed_from_date"],
        missing=missing,
    )

    severity_rank = SEVERITY_RANK
    findings = sorted(
        cost_block["findings"],
        key=lambda finding: (severity_rank[finding["severity"]], finding["item_id"], finding["rule"]),
    )
    status = "computed" if not missing and cash_path["determinate"] else "indeterminate"
    return {
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "grant": {
            "label": grant["label"],
            "decision_date": grant["decision_date"].isoformat(),
            "project_start_date": grant["project_start"].isoformat(),
            "project_end_date": grant["project_end"].isoformat(),
            "report_due_date": grant["report_due"].isoformat(),
            "expected_payment_date": (
                grant["expected_payment_date"].isoformat()
                if grant["expected_payment_date"] is not None
                else None
            ),
            "expected_payment_evidence": grant["expected_payment_evidence"],
        },
        "subsidy_estimate": estimate,
        "cost_items": [
            {key: value for key, value in item.items() if key != "payment_month_index"}
            for item in items
        ],
        "risk_findings": findings,
        "clawback_exposure": exposure,
        "evidence_gaps": cost_block["evidence_gaps"],
        "cash_path": cash_path,
        "financing_options": options,
        "latest_arrangement_date": latest_arrangement,
        "status": status,
        "missing_inputs": missing,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: plan_grant_execution.py <input.json>", file=sys.stderr)
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
