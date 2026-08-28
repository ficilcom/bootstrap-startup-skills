# Four Gap Skills Design

## Goal

Add four independently installable skills that close gaps in annual planning cadence, customer security due diligence, sell-side contract terms, and engagement-structure risk. Each skill must preserve evidence provenance, localize unknowns, keep gates separate from economics, and stop before external changes.

## Common contract

- Each deterministic helper accepts an optional `analysis_mode` of `core` or `advanced`; omission means `core`.
- Numeric inputs use `{value, evidence}` or `{amount, currency, evidence}` with `confirmed`, `reported`, `estimated`, and `unknown`.
- An `unknown` numeric input has a null numeric field and never becomes zero.
- Each result includes `analysis_quality` with `mode`, `status`, `evidence_counts`, `decision_changing_unknowns`, and `warnings`.
- Duplicate identifiers, invalid references, contradictory thresholds, invalid dates or periods, currency mismatches, and malformed CLI inputs fail explicitly.
- Economic ordering remains separate from requirement gates, risk flags, and recommendations, and each result names its own comparison scope.
- No helper contacts customers, candidates, contractors, or authorities; answers a questionnaire; signs or amends a contract; changes payroll or insurance records; or moves money.
- Python code is duplicated locally where needed; no runtime dependency is shared across skills.

## 1. Annual operating plan

Location: `skills/management/annual-operating-plan/`.

Core inputs define a fiscal year start, currency, opening cash, minimum cash buffer, revenue streams with twelve monthly amounts and a gross margin rate, twelve fixed-cost months, committed outflows placed on a month index, and user-supplied annual targets for revenue, gross profit, and ending cash. The helper builds monthly gross profit, operating cash, and ending cash; reports minimum cash and the first buffer breach month; aggregates quarters; and reports for each target whether the assembled arithmetic reaches it and by how much it falls short.

Advanced inputs add scenarios with revenue, margin, and cost adjustments plus quarterly checkpoints with a metric, threshold, and revision trigger. Advanced results compare each scenario's cash path and buffer breach and evaluate each checkpoint against the planned quarter value.

The helper never calls a target achievable. It reports arithmetic reach and cash survivability as two separate results. It does not re-forecast weekly cash and does not rank investment candidates.

## 2. Security questionnaire readiness

Location: `skills/operations/security-questionnaire-readiness/`.

Core inputs define a basis date, submission deadline, available hours per week, and questionnaire items with a category, requirement level, current state, evidence artifact, and remediation hours. An item counts as answerable now only when it is implemented and has a usable evidence artifact; `partial` never rounds up to implemented. The helper returns category coverage, must gaps that block the deal, total remediation hours, required weeks against weeks available, the first item that cannot fit before the deadline, and a priority-ordered remediation schedule.

Advanced inputs add per-item remediation cost, compensating controls with customer acceptance state, and owners. Advanced results separate must gaps covered by an accepted compensating control from those that remain, and total the remediation cost.

The helper does not certify compliance, does not answer the questionnaire, and never treats an undocumented control as implemented.

## 3. Customer contract terms review

Location: `skills/sales/customer-contract-terms-review/`.

Core inputs define a basis date, currency, a contract with value, duration, a billing schedule by month index, payment terms days, acceptance lag days, and delivery costs by month, plus user-defined policy floors. The helper converts each billing event into a cash-receipt month using acceptance lag and payment terms, builds the cumulative cash path, and returns the peak funded amount and the month it occurs, days to first cash, and every breached policy floor.

Advanced inputs add liability cap with an explicit `capped`, `uncapped`, or `unknown` type, termination notice days, auto-renewal and renewal term, IP assignment, subcontracting, and annual revenue. Advanced results report liability exposure against contract value and annual revenue, unrecovered cost at the earliest permitted termination, committed months under auto-renewal, and clause risk flags ordered by exposure separately from the flags themselves.

`uncapped` and `unknown` are never merged. The helper does not judge clause validity or enforceability.

## 4. Contractor or employment structuring

Location: `skills/hiring/contractor-or-employment-structuring/`.

Core inputs define currency, an engagement with monthly fee and elapsed and remaining months, and observations against a fixed factor enum covering direction and control, work discretion, time and place constraints, remuneration character, exclusivity, substitutability, and equipment burden. Each observation is `independent`, `mixed`, `employment_like`, or `unknown` with evidence. The helper tallies observations, lists employment-like factors with their evidence state, and lists unknown factors that could change the picture.

Advanced inputs add user-supplied reclassification cost assumptions and mitigations that name the factor ids they address. Advanced results give base and downside retroactive cost from those assumptions only, compare it against the engagement's remaining fee, and report for each mitigation which employment-like factors it covers and which remain.

The helper does not determine classification, does not substitute for an administrative or judicial decision, does not resolve factors by majority, and collects no personal or protected data.

## Documentation and validation

Each skill has a concise `SKILL.md`, one deterministic script, four directly linked references for intake, calculation, a topic file, and reporting, and a test file under the matching repository test path. README gains one row per skill. Each skill is validated before work moves to the next, followed by a repository-wide validator run, a full test run, realistic core and advanced executions, unknown-localization checks, and a link check.
