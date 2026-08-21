# Cash Runway Planner Design

Date: 2026-08-22  
Status: Accepted for implementation

## Purpose

Create a portable `cash-runway-planner` skill for bootstrapped and capital-efficient businesses. The skill converts available cash data and explicit assumptions into a short-term cash forecast, a medium-term runway estimate, configurable warning lines, and a dated action plan.

The skill must answer four operating questions:

1. How much unrestricted cash is available now?
2. When will cash fall below the operating buffer or zero under each scenario?
3. Which receipts, payments, or assumptions cause the pressure?
4. Which authorized actions could extend runway, by how much, and by when must they start?

## Scope

### Included

- A 13-week, cash-basis forecast for near-term liquidity.
- A monthly extension through month 12 for medium-term runway.
- Base, downside, and optional upside scenarios.
- Separate dates for crossing the minimum cash buffer and crossing zero.
- A provisional quick mode when only balances and monthly estimates are available.
- A detailed mode using dated or weekly cash movements.
- A prioritized action register with timing, cash effect, trade-offs, and owner decisions.
- Deterministic calculations from an anonymous JSON input.
- Clear separation of confirmed, reported, estimated, and unknown information.

### Excluded

- Accounting profit forecasts, balance-sheet forecasts, or statutory cash-flow statements.
- Tax, legal, insolvency, or payroll compliance determinations.
- Automatic cancellation, payment deferral, financing applications, vendor contact, or other external action.
- Claims that a forecast is a guarantee or that a warning band is a universal standard.
- Valuation, fundraising probability, or loan approval prediction.
- SaaS-only metrics such as MRR, CAC, or LTV unless the user supplies them as context for a cash assumption.

## Intended users and requests

The skill is industry-neutral and applies to founders and small operating teams that need to forecast liquidity, estimate runway, test a downside case, or decide when to reduce or defer spending. It supports SaaS, services, commerce, and mixed business models because all calculations operate on cash receipts and payments.

The description should activate for requests such as:

- “How many months of runway do we have?”
- “Build a 13-week cash-flow forecast.”
- “When do we need to start cutting costs?”
- “What happens if collections slip by four weeks?”
- “How much runway would these reductions add?”

It should not activate for requests limited to accounting cash-flow statement preparation, investment return analysis, or personal household budgeting.

## Skill structure

```text
skills/finance/cash-runway-planner/
├── SKILL.md
├── references/
│   ├── intake.md
│   ├── calculation-model.md
│   ├── action-ladder.md
│   └── report-format.md
└── scripts/
    ├── calculate_runway.py
    └── test_calculate_runway.py
```

`SKILL.md` contains only the shared workflow, routing rules, essential constraints, and authorization boundary. Detailed input guidance, formulas, action evaluation, and output structure live in the linked references. The Python script owns repeatable arithmetic and validation.

The repository `README.md` will list the skill after implementation.

## Operating workflow

1. Read `references/intake.md` and inspect user-provided materials before asking questions.
2. Establish the as-of date, forecast currency, unrestricted opening cash, restricted cash, minimum operating buffer, known receipts, known payments, and recurring assumptions.
3. Classify each material input as `confirmed`, `reported`, `estimated`, or `unknown`. Do not convert unknown values to zero.
4. Select `quick` or `detailed` mode.
5. Build at least a base scenario. Add a downside scenario whenever collection timing, revenue, or a material payment is uncertain enough to change the decision. Add an upside scenario only when useful to the user.
6. Write the minimum necessary anonymous input JSON outside the skill directory and run `scripts/calculate_runway.py`.
7. Resolve validation errors by correcting inputs or keeping the conclusion provisional; do not invent missing facts.
8. Read `references/action-ladder.md`, evaluate relevant actions, and rerun modeled actions when their timing and amount are sufficiently specified.
9. Read `references/report-format.md` and produce the report in its prescribed order.
10. Obtain explicit authorization before any external communication, cancellation, payment change, application, or transaction.

## Modes

### Quick mode

Use quick mode when the user cannot yet provide a dated 13-week schedule. Minimum usable inputs are:

- as-of date;
- gross cash and any restricted cash, from which opening available cash is derived;
- an estimated normal monthly cash inflow;
- an estimated normal monthly cash outflow; and
- known material one-time receipts or payments.

Quick mode produces a provisional estimate. It must state that monthly averages can hide weekly payment pressure. If an unknown item could materially alter the result, identify it and do not imply false precision.

### Detailed mode

Use detailed mode when dated transactions or weekly amounts are available for the first 13 weeks. After week 13, use explicit monthly assumptions through month 12. Detailed mode must preserve timing rather than spreading known receipts or payments evenly.

## Data and evidence model

### Cash definitions

- `gross_cash`: cash and cash equivalents represented by the user’s source data.
- `restricted_cash`: cash that cannot be used for ordinary operating payments.
- `opening_available_cash`: `gross_cash - restricted_cash`.
- `minimum_cash_buffer`: a user-set operating reserve. It is not an expense and does not reduce the projected balance.
- `closing_available_cash`: the available balance after cash receipts and payments for a period.

Restricted cash and the minimum cash buffer must remain separate. Crossing the buffer is a warning event; crossing zero is a liquidity event.

### Evidence states

- `confirmed`: supported by a supplied record or directly observable source.
- `reported`: stated by the user without supporting material.
- `estimated`: a forecast assumption rather than a known amount.
- `unknown`: missing or unresolved.

Zero is a valid amount only when explicitly known or estimated as zero. An omitted amount is `unknown`, not zero.

### Scenario ownership

Each cash movement belongs to one or more named scenarios. Shared known movements may appear in every scenario. Scenario-specific assumptions must not silently overwrite confirmed movements.

## Calculation model

### Period balances

For every weekly or monthly period:

```text
closing_available_cash
= opening_available_cash
+ total_cash_inflows
- total_cash_outflows
```

The next period opens with the previous period’s closing balance. Calculations use the stated currency’s ordinary decimal precision and must not mix currencies. If source amounts use multiple currencies, the user must supply an exchange-rate assumption and conversion date or receive separate forecasts.

### Forecast horizons

- Weeks 1–13: weekly periods beginning from the as-of date.
- Months 4–12: monthly periods continuing after the end of week 13 without overlapping it.

The implementation must define period boundaries deterministically, including partial first weeks, in `references/calculation-model.md` and test boundary dates.

### Runway events

For each scenario calculate:

- first period ending below `minimum_cash_buffer`;
- first period ending below zero;
- lowest closing balance and its period;
- maximum funding gap required to remain at or above the buffer;
- last modeled period; and
- the difference from the base scenario.

When a threshold is crossed within a period, interpolation may be shown only as an estimate and only when the period’s net movement is treated as uniform. The authoritative result remains the period-end crossing.

If neither threshold is crossed within 12 months, report `more_than_12_months` rather than infinity or an unsupported extrapolation.

The maximum funding gap is `max(0, minimum_cash_buffer - lowest_closing_available_cash)` within the modeled horizon.

### Runway months

Runway months are the elapsed days from the as-of date to the relevant estimated crossing date divided by `30.4375`. The report rounds to one decimal place while retaining unrounded values in script output.

### Warning status

The primary status is driven by the earliest buffer or zero crossing:

- `critical`: the first crossing occurs within 13 weeks.
- `warning`: the first crossing occurs after 13 weeks but before 6 months.
- `watch`: the first crossing occurs from 6 months through the end of month 12.
- `stable`: neither threshold is crossed within the modeled horizon.
- `indeterminate`: missing information prevents a defensible threshold result.

These are operating defaults, not professional or universal standards. A user-provided policy overrides them and must be recorded in the report.

### Modeled actions

An action may be included in recalculation only when all of the following are specified:

- amount or calculation rule;
- cash-effective date or period;
- recurrence or duration;
- scenario applicability; and
- any one-time implementation cost.

The script returns the change in buffer-crossing date, zero-crossing date, lowest balance, and funding gap. It does not decide whether the action is commercially or legally acceptable.

## Action framework

Actions are evaluated in this order, while allowing user constraints to override the order:

1. Accelerate legitimate collections and resolve overdue receivables.
2. Remove unused or low-value discretionary spend.
3. Defer uncommitted hiring, equipment, or projects.
4. Renegotiate vendor terms or restructure fixed costs.
5. Consider deeper reductions that could affect revenue, customers, staff, or continuity.
6. Compare financing only when operational measures do not close the gap or financing is already part of the user’s plan.

For each relevant action, record:

- decision deadline;
- cash-effective date;
- gross and net cash effect;
- one-time cost;
- lead time and contractual dependency;
- expected revenue, customer, staff, or operating impact;
- confidence and evidence state;
- owner decision required; and
- modeled runway extension, when calculable.

Mandatory, contractual, payroll, tax, debt-service, and safety-critical payments must not be labeled safe to defer or cut. The report may flag them for professional review or negotiation without asserting that non-payment is permitted.

## Script interface

`calculate_runway.py` accepts one JSON input path and writes JSON to standard output. It must use only the Python standard library.

The top-level input contains:

- `mode`;
- `as_of_date`;
- `currency`;
- `gross_cash` and its evidence state;
- `restricted_cash` and its evidence state;
- `minimum_cash_buffer` and its evidence state;
- `scenarios`, each containing ordered periods and movements; and
- optional `modeled_actions`.

Each movement contains a stable identifier, label, direction, amount, evidence state, date or period, recurrence information when applicable, and scenario applicability.

The script must reject:

- malformed dates or JSON;
- unsupported evidence states or modes;
- negative cash movement amounts;
- duplicate movement or action identifiers;
- mixed or missing currencies;
- overlapping period definitions;
- a restricted cash amount greater than gross cash;
- unknown values passed as numeric zero;
- fewer than 13 weekly periods in detailed mode;
- gaps or disorder in the period sequence; and
- actions without enough timing or amount data to model.

Validation errors go to standard error and return a nonzero exit status. No partial numerical conclusion is returned after a validation failure.

## Report contract

The report is written in the user’s language and presents:

1. decision summary;
2. data quality and provisional status;
3. available cash and buffer;
4. scenario comparison;
5. 13-week weekly forecast;
6. monthly runway through month 12;
7. pressure points and their causes;
8. warning line and decision deadlines;
9. prioritized actions and modeled effects;
10. unknowns, sensitivities, and next evidence to collect; and
11. authorization boundary and professional-review items.

The report must show important formulas and assumptions, but it should not reproduce sensitive source data or anonymous working-file paths unless the user requests them.

## Safety and authorization

- Collect only the data needed for the forecast. Do not request account numbers, card details, authentication data, personal identifiers, or unrelated employee information.
- Treat payroll, taxes, debt payments, regulated obligations, and insolvency indicators as high-consequence items. Describe uncertainty and recommend qualified review when the decision depends on jurisdiction-specific rules.
- Verify current authoritative sources only when the task depends on current tax, legal, grant, financing, or regulatory facts. Record the access date and source.
- Do not contact customers, staff, vendors, lenders, advisers, or authorities without explicit authorization.
- Do not cancel services, move funds, change payment timing, submit applications, or initiate transactions without explicit authorization immediately before the action.

## Testing and acceptance criteria

### Deterministic script tests

`test_calculate_runway.py` must cover at least:

1. stable detailed forecast with no crossing inside 12 months;
2. buffer crossing inside 13 weeks without a zero crossing;
3. zero crossing and correct maximum funding gap;
4. downside collection delay that changes the warning status;
5. one-time payment on a period boundary;
6. restricted cash separated from the operating buffer;
7. an action with a one-time cost and recurring savings;
8. quick-mode provisional output;
9. rejection of unknown values encoded as zero;
10. rejection of malformed, overlapping, incomplete, or duplicate input.

Tests must assert calculated values and invariants, not report wording.

### Behavioral exercises

Exercise the completed skill with at least two realistic requests:

- a bootstrapped SaaS company with delayed receivables, annual software renewals, and a planned hire;
- a services company with uneven project collections, contractor payments, and tax-related uncertainty.

Inspect whether the result distinguishes cash timing from accounting revenue, labels estimates, avoids false precision, provides dated actions, and preserves authorization boundaries.

### Repository validation

Run:

```bash
python3 scripts/validate_skills.py
```

The implementation is complete when the repository validator passes, all deterministic tests pass, the two behavioral exercises produce usable reports, the `README.md` lists the new skill, and no scaffold placeholders remain.
