# Five Decision Skills Design

## Goal

Add five independently installable skills that close gaps in growth experimentation, deal qualification, hiring selection, delivery capacity, and working-capital decisions. Each skill must preserve evidence provenance, localize unknowns, expose decision gates, and stop before external changes.

## Common contract

- Each deterministic helper accepts an optional `analysis_mode` of `core` or `advanced`; omission means `core`.
- Numeric inputs use `{value, evidence}` or `{amount, currency, evidence}` with `confirmed`, `reported`, `estimated`, and `unknown`.
- An `unknown` numeric input has a null numeric field and never becomes zero.
- Each result includes `analysis_quality` with `mode`, `status`, `evidence_counts`, `decision_changing_unknowns`, and `warnings`.
- Duplicate identifiers, invalid references, contradictory thresholds, invalid dates or periods, and malformed CLI inputs fail explicitly.
- Economic ordering remains separate from eligibility, process gates, risk flags, and recommendations.
- No helper contacts customers or candidates, launches experiments, changes CRM or hiring systems, accepts work, hires capacity, changes payment terms, or moves money.
- Python code is duplicated locally where needed; no runtime dependency is shared across skills.

## 1. Growth experiment review

Location: `skills/marketing/growth-experiment-review/`.

Core inputs define currency, horizon, internal hourly cost, execution capacity, and experiments. Each experiment has an ID, status, cash cost, effort, potential gross contribution, and user-supplied success probability. The helper calculates internal cost, total cost, expected net value, capacity gap, and an economic order without treating that order as a launch recommendation.

Advanced inputs add required and available sample, observed metric, success and stop thresholds, and user-defined probability/contribution/cost scenarios. Completed experiments with sufficient samples can produce `scale`, `stop`, or `inconclusive`; proposed experiments can produce `run` or `hold`. Missing decision inputs remain local to the affected experiment or scenario.

## 2. Sales deal qualification

Location: `skills/sales/sales-deal-qualification/`.

Inputs define a basis date, forecast end date, currency, must/should qualification criteria, a founder-intervention amount threshold, and anonymized deals. Each deal has an ID, customer ID, amount, user-supplied stage probability, close date, next-action date, and criterion results of `verified`, `reported`, `unknown`, or `failed`.

Must failures disqualify a deal; unverified must criteria make it conditional. The helper preserves weighted value without changing the supplied probability, flags overdue or out-of-period timing, and returns `continue`, `hold`, `exit`, or `founder_intervention`. Advanced checks cover decision process, mutual action plan, and commercial terms. No CRM or customer action is performed.

## 3. Role scorecard and hiring process

Location: `skills/hiring/role-scorecard-and-hiring-process/`.

Inputs define a role, weighted outcome/competency/must criteria, minimum ratings, and anonymized candidate evaluations. Ratings use evidenced scalar values. Missing or failed must evidence controls eligibility separately from the weighted score, so an impressive average cannot erase a hard gate.

Advanced inputs add required process checks such as a work sample, structured interview, references, compensation approval, or conflict review. Outputs include candidate evidence scores, eligibility, failed and unknown gates, ranking scope, process gaps, decision signals, and stopping conditions. Protected traits and unnecessary personal data are excluded; no outreach, rejection, offer, or HR-system update occurs.

## 4. Capacity and backlog plan

Location: `skills/operations/capacity-and-backlog-plan/`.

Inputs define period units, horizon periods, per-period internal and external capacity, and work items classified as committed, backlog, or qualified. Work has an ID, due period, required hours, and optional contribution. The helper calculates period and cumulative demand, capacity gaps, first breach, and at-risk work without inventing a schedule for unknown hours.

Advanced inputs add interventions with start period, incremental capacity, and cost, plus user-defined demand/capacity scenarios. Outputs compare intervention and scenario coverage while keeping service, quality, people, and contractual gates separate. The helper does not accept orders, change delivery commitments, procure vendors, authorize overtime, or create requisitions.

## 5. Working capital cycle review

Location: `skills/finance/working-capital-cycle-review/`.

Core inputs define currency, measurement days, revenue, cost of goods sold, receivables, inventory, payables, and customer deposits. The helper calculates DSO, DIO, DPO, cash conversion cycle, and net working capital. Zero revenue or cost bases make only the affected ratios indeterminate.

Advanced inputs add user-defined DSO, DIO, DPO, and deposit targets plus balance scenarios. The helper calculates signed cash-release components, scenario cycle metrics, and validation or negotiation targets. It does not present targets as universally good, and it does not change invoices, supplier terms, inventory orders, banking, accounting, or tax records.

## Documentation and validation

Each skill has a concise `SKILL.md`, a deterministic script, three directly linked references for intake, calculation, and reporting/decision rules, and a test file under the matching repository test path. README gains one row per skill. Each skill is validated before work moves to the next, followed by a fresh repository-wide validator, full test run, link check, diff check, and realistic advanced executions.
