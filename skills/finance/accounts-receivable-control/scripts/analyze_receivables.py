#!/usr/bin/env python3
"""Analyze open receivables, aging, commitments, and near-term cash impact."""

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
AGING_BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "over_90")


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


def _money(value: object, path: str, currency: str) -> tuple[Decimal | None, str]:
    item = _object(value, path)
    evidence = item.get("evidence")
    if evidence not in EVIDENCE_STATES:
        raise ValueError(f"{path}.evidence must be a supported evidence state")
    if item.get("currency") != currency:
        raise ValueError(f"{path}.currency must match currency")
    amount = item.get("amount")
    if evidence == "unknown":
        if amount is not None:
            raise ValueError(f"{path}.amount must be null when evidence is unknown")
        return None, evidence
    if amount is None:
        raise ValueError(f"{path}.amount is required unless evidence is unknown")
    return _decimal(amount, f"{path}.amount"), evidence


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral() else float(value)


def _bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return "current"
    if days_past_due <= 30:
        return "days_1_30"
    if days_past_due <= 60:
        return "days_31_60"
    if days_past_due <= 90:
        return "days_61_90"
    return "over_90"


def calculate(payload: object) -> dict[str, Any]:
    data = _object(payload, "input")
    as_of = _date(data.get("as_of_date"), "as_of_date")
    currency = _string(data.get("currency"), "currency")
    if not CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter uppercase code")

    missing: list[str] = []
    seen_ids: set[str] = set()
    invoice_results: list[dict[str, Any]] = []
    known_aging = {bucket: Decimal(0) for bucket in AGING_BUCKETS}
    customer_known: dict[str, Decimal] = defaultdict(Decimal)
    customer_indeterminate: set[str] = set()
    known_outstanding = Decimal(0)
    all_outstanding_known = True
    commitments = {"confirmed": Decimal(0), "reported": Decimal(0), "estimated": Decimal(0)}

    for index, raw_invoice in enumerate(_list(data.get("invoices"), "invoices")):
        path = f"invoices[{index}]"
        invoice = _object(raw_invoice, path)
        invoice_id = _string(invoice.get("id"), f"{path}.id")
        if invoice_id in seen_ids:
            raise ValueError("invoice ids must be unique")
        seen_ids.add(invoice_id)
        customer_id = _string(invoice.get("customer_id"), f"{path}.customer_id")
        issued = _date(invoice.get("issued_date"), f"{path}.issued_date")
        due = _date(invoice.get("due_date"), f"{path}.due_date")
        if issued > as_of:
            raise ValueError(f"{path}.issued_date cannot be after as_of_date")
        if due < issued:
            raise ValueError(f"{path}.due_date cannot precede issued_date")

        original, _ = _money(invoice.get("original_amount"), f"{path}.original_amount", currency)
        paid, _ = _money(invoice.get("paid_amount"), f"{path}.paid_amount", currency)
        if original is not None and paid is not None and paid > original:
            raise ValueError(f"{path}.paid_amount cannot exceed original_amount")
        outstanding = original - paid if original is not None and paid is not None else None
        days_past_due = (as_of - due).days
        bucket = _bucket(days_past_due)
        flags: list[str] = []

        commitment_result: dict[str, Any] | None = None
        if "payment_commitment" in invoice:
            commitment = _object(invoice.get("payment_commitment"), f"{path}.payment_commitment")
            commitment_date = _date(commitment.get("date"), f"{path}.payment_commitment.date")
            commitment_amount, commitment_evidence = _money(
                commitment.get("amount"), f"{path}.payment_commitment.amount", currency
            )
            if commitment_amount is not None and outstanding is not None and commitment_amount > outstanding:
                raise ValueError(f"{path}.payment_commitment.amount cannot exceed outstanding")
            if commitment_amount is None:
                missing.append(f"{path}.payment_commitment.amount")
            elif commitment_evidence in commitments:
                commitments[commitment_evidence] += commitment_amount
            if commitment_date < as_of and (outstanding is None or outstanding > 0):
                flags.append("commitment_missed")
            commitment_result = {
                "date": commitment_date.isoformat(),
                "amount": _number(commitment_amount),
                "evidence": commitment_evidence,
            }

        if days_past_due > 30 and (outstanding is None or outstanding > 0):
            flags.append("over_30_days_past_due")
        disputed = invoice.get("disputed", False)
        if not isinstance(disputed, bool):
            raise ValueError(f"{path}.disputed must be boolean")
        if disputed and (outstanding is None or outstanding > 0):
            flags.append("disputed")

        if outstanding is None:
            all_outstanding_known = False
            customer_indeterminate.add(customer_id)
            missing.append(
                f"{path}.original_amount" if original is None else f"{path}.paid_amount"
            )
        else:
            known_outstanding += outstanding
            known_aging[bucket] += outstanding
            customer_known[customer_id] += outstanding

        invoice_results.append(
            {
                "id": invoice_id,
                "customer_id": customer_id,
                "outstanding": _number(outstanding),
                "days_past_due": max(days_past_due, 0),
                "aging_bucket": bucket,
                "payment_commitment": commitment_result,
                "flags": flags,
            }
        )

    customers = []
    for customer_id in sorted(set(customer_known) | customer_indeterminate):
        amount = customer_known[customer_id]
        share = amount / known_outstanding if known_outstanding else None
        customers.append(
            {
                "customer_id": customer_id,
                "known_outstanding": _number(amount),
                "share_of_known_outstanding": round(float(share), 6) if share is not None else None,
                "complete": customer_id not in customer_indeterminate,
            }
        )
    customers.sort(key=lambda item: (-item["known_outstanding"], item["customer_id"]))

    cash_impact: dict[str, Any] | None = None
    if "cash_context" in data:
        context = _object(data.get("cash_context"), "cash_context")
        available, _ = _money(context.get("available_cash"), "cash_context.available_cash", currency)
        buffer, _ = _money(context.get("minimum_cash_buffer"), "cash_context.minimum_cash_buffer", currency)
        obligations, _ = _money(
            context.get("near_term_obligations"), "cash_context.near_term_obligations", currency
        )
        if available is None or buffer is None or obligations is None:
            missing.append("cash_context")
        else:
            before = available - obligations
            after = before + commitments["confirmed"]
            cash_impact = {
                "cash_before_receipts": _number(before),
                "buffer_gap_before_receipts": _number(max(buffer - before, Decimal(0))),
                "cash_after_confirmed_commitments": _number(after),
                "buffer_gap_after_confirmed_commitments": _number(max(buffer - after, Decimal(0))),
            }

    return {
        "status": "complete" if all_outstanding_known and not missing else "indeterminate",
        "as_of_date": as_of.isoformat(),
        "currency": currency,
        "total_outstanding": _number(known_outstanding) if all_outstanding_known else None,
        "known_outstanding": _number(known_outstanding),
        "aging_buckets": {key: _number(value) for key, value in known_aging.items()},
        "commitments_by_evidence": {key: _number(value) for key, value in commitments.items()},
        "cash_impact": cash_impact,
        "customers": customers,
        "invoices": invoice_results,
        "missing_inputs": sorted(set(missing)),
    }


def main(argv: list[str] | None = None) -> int:
    parser_argv = sys.argv[1:] if argv is None else argv
    if len(parser_argv) != 1:
        print("usage: analyze_receivables.py <input.json>", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(parser_argv[0]).read_text(encoding="utf-8"))
        result = calculate(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
