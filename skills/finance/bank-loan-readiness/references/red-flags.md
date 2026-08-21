# Loan-readiness red flags

Use a red flag only when its evidence is `confirmed` (supported by records or independently verifiable information) or `reported` (directly stated by the applicant or responsible manager). Send it to the scoring script exactly as:

```json
{"code":"example_code","severity":"major","evidence":"confirmed"}
```

Permitted severities are `major` and `critical`; permitted red-flag evidence values are `confirmed` and `reported`. Record `unknown` or `inferred` concerns only in an unresolved-questions list, not in `red_flags`. The scorer's caps describe readiness and do not encode automatic lender rejection.

## Flag catalog

### `current_serious_delinquency` — critical

**Use when:** a current serious delinquency on taxes, social insurance, debt, lease, or other material obligation is confirmed or reported.

**Why it matters:** it may signal immediate repayment, legal, cash-flow, and reliability risk.

**Clarify:** What obligation is delinquent, for how long and how much? Is it current, disputed, on an agreed plan, or cured? What evidence documents the status?

**Remediate:** obtain current statements or settlement documentation, cure or formalize a repayment arrangement where appropriate, and rebuild the cash forecast with the obligation included.

### `material_misrepresentation` — critical

**Use when:** a material false or misleading declaration, fabricated document, or deliberate omission affecting the application is confirmed or reported.

**Why it matters:** reliable underwriting depends on truthful and complete information.

**Clarify:** Which statement or document conflicts with what source? Is the difference material, intentional, and unresolved? Who prepared it?

**Remediate:** stop relying on the affected submission, correct the record with source documents, explain the discrepancy, and obtain professional advice where needed.

### `ineligible_or_illegal_use` — critical

**Use when:** the requested funds are confirmed or reported to be for an unlawful, prohibited, fraudulent, or clearly ineligible use.

**Why it matters:** such use may prevent a lawful, supportable financing transaction.

**Clarify:** What is the precise use, recipient, timing, and governing restriction? Can it be separated from eligible business uses?

**Remediate:** remove the use from the request, redesign the sources-and-uses schedule for eligible purposes, and seek qualified legal or program guidance if legality is uncertain.

### `missing_required_license` — critical when operation is unlawful; otherwise major

**Use when:** a required license or permit is confirmed or reported as missing, expired, or suspended. Set `critical` only when the missing authorization makes the present or proposed operation unlawful; otherwise set `major`. A lack of documentary proof alone is `unknown`, not a red flag; ask for the authorization or an authoritative requirement check.

**Why it matters:** missing authority can interrupt operations, revenue, insurance, and enforceability.

**Clarify:** Which license is required, by which authority, for which activity and location? Is an application pending, and may the activity legally proceed in the meantime?

**Remediate:** confirm the requirement with the competent authority, obtain or renew the authorization before operating where required, and revise timing and cash flow to reflect the status.

### `tax_or_social_insurance_arrears` — major

**Use when:** tax or social-insurance arrears are confirmed or reported, except use `current_serious_delinquency` if the circumstance meets that higher-severity definition.

**Why it matters:** arrears can reduce cash available for debt service and signal compliance risk.

**Clarify:** What authority, amount, periods, due dates, penalties, payment-plan status, and evidence apply? Are all current filings made?

**Remediate:** obtain official balances, correct filings, pay or formalize an arrangement as appropriate, and include the resulting payments in cash flow.

### `unsupported_debt_service` — major

**Use when:** confirmed or reported cash-flow evidence shows that existing plus requested debt service cannot be covered, or the applicant confirms that no substantive repayment basis or model exists. Unavailable support documents alone remain `unknown` and unresolved; they do not establish this flag.

**Why it matters:** a request without plausible debt-service capacity is not loan-ready.

**Clarify:** What cash generation is normalized, which debt payments are included, how are seasonal needs treated, and what happens in a downside case?

**Remediate:** reconcile statements and debt schedule, correct forecasts, reduce or restructure the request where appropriate, and demonstrate a credible cash buffer.

### `unexplained_material_inconsistency` — major

**Use when:** a material contradiction across declarations, statements, schedules, applications, or supporting documents is confirmed or reported and remains unexplained.

**Why it matters:** inconsistencies undermine reliance on projections, repayment analysis, and compliance assertions.

**Clarify:** Which figures or declarations conflict, what period and source does each represent, and is there a legitimate reconciliation?

**Remediate:** prepare a documented reconciliation, correct erroneous records, and ensure every affected schedule, forecast, and declaration uses the same basis.

### `unclear_use_of_funds` — major

**Use when:** the requested amount, recipient, timing, or business purpose is confirmed or reported as vague, unsupported, or not reconcilable to sources and uses.

**Why it matters:** a lender cannot assess suitability, term, amount, or repayment linkage without a clear use.

**Clarify:** What will each amount buy or fund, when is it needed, who will receive it, what quote or calculation supports it, and what alternatives exist?

**Remediate:** prepare an itemized sources-and-uses schedule, collect quotations or calculations for material items, separate working capital from fixed assets, and align requested timing and term to the use.

## Applying flags

Do not infer a flag from a low criterion rating alone. For each applied flag, preserve the source and short factual basis in the assessment narrative, then emit only its code, severity, and `confirmed` or `reported` evidence to the script. If a concern is plausible but not established, ask a targeted question and list it as unresolved. Multiple flags may be sent when independently supported; do not add new severities or evidence labels.
