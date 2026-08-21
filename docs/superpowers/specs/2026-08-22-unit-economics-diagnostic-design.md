# Unit Economics Diagnostic Design

Date: 2026-08-22  
Status: Accepted for implementation

## Purpose

Create a portable `unit-economics-diagnostic` skill for bootstrapped and capital-efficient businesses. The skill determines whether an economic unit creates contribution profit, whether acquisition cost can be recovered within a credible customer relationship, whether fixed costs can be covered at feasible volume, and which assumptions can reverse the conclusion.

The skill must answer five operating questions:

1. What is the economic unit, and how much gross and contribution profit does one unit create?
2. Which customer acquisition cost definition is being used, and when is it recovered?
3. What lifetime value method is defensible for the available evidence?
4. What sales volume or revenue covers fixed costs, and is that volume feasible?
5. Which price, cost, acquisition, retention, or volume assumptions most affect the decision to scale?

## Scope

### Included

- Industry-neutral analysis with `recurring`, `transactional`, and `service_project` modes.
- Explicit economic-unit and revenue-basis selection.
- Gross profit, gross margin, contribution profit, and contribution margin.
- `paid`, `blended`, `fully_loaded`, and `marginal` CAC definitions without mixing scopes.
- CAC payback using contribution profit rather than revenue.
- Observed-cohort, fixed-horizon, and constant-retention LTV methods.
- LTV-to-CAC comparison when both inputs use compatible customer scope and economics.
- Break-even unit volume and revenue, including an infeasible-break-even result when contribution is not positive.
- Capacity comparison when the user provides a credible capacity limit.
- Base and downside scenarios plus optional upside scenarios.
- Independently recalculated sensitivity cases and decision breakpoints.
- Deterministic calculations from anonymous JSON.
- Clear separation of `confirmed`, `reported`, `estimated`, and `unknown` information.

### Excluded

- Statutory accounting, tax-return classification, audited gross margin, or professional accounting determinations.
- Company valuation, fundraising probability, market sizing, or cash-runway forecasting.
- A universal target such as “LTV:CAC must exceed 3” or “payback must be under 12 months.”
- Infinite LTV when observed churn is zero.
- Automatic price, advertising, budget, product, hiring, or sales-channel changes.
- Consolidation of unlike economic units into one blended result without an explicit, supportable allocation basis.

## Intended users and requests

The skill applies when a founder or operating team asks whether selling more improves economics, whether customer acquisition is recoverable, which price or cost must change, what volume reaches operating break-even, or which assumptions make growth unattractive.

The description should activate for requests such as:

- “Do we make money on every customer?”
- “Calculate gross margin and contribution margin.”
- “What is our fully loaded CAC and payback?”
- “Estimate LTV without overstating it.”
- “How many subscriptions, orders, or projects reach break-even?”
- “What happens if price drops, fulfillment cost rises, or churn worsens?”

It should not activate for personal-investment returns, securities valuation, statutory financial statements, or a request limited to cash depletion timing.

## Approach and mode selection

The implementation uses a shared driver model with mode-specific interpretation rather than unrelated calculators. Each run analyzes one economic unit and one revenue stream. A hybrid business runs the skill separately for each materially different stream. Consolidation is a later management-analysis step and is not part of the first version.

### `recurring`

Use for subscriptions, memberships, retainers, maintenance, and other repeating customer-period economics. The normal unit is a customer-period, seat-period, or account-period. Constant-retention LTV is allowed only when churn is positive, measured over a consistent period, and credible enough for the decision.

### `transactional`

Use for orders, transactions, marketplace activity, usage, or one-time product sales. The unit is an order, transaction, item, or another consistently measured event. LTV normally uses observed cohort contribution or expected units per customer over an explicit horizon.

For a marketplace, the revenue basis is the company’s fee, commission, spread, or other recognized economic revenue unless the business is the principal for the underlying sale. GMV must not silently become company revenue.

### `service_project`

Use for projects, engagements, billable blocks, jobs, or professional-service relationships. Direct delivery labor and contractors attributable to the unit belong in COGS or unit-variable cost, not fixed overhead merely because they are paid through payroll. Capacity is especially important because a mathematically positive break-even point may exceed deliverable hours or projects.

## Skill structure

```text
skills/finance/unit-economics-diagnostic/
├── SKILL.md
├── references/
│   ├── intake.md
│   ├── model-selection.md
│   ├── calculation-model.md
│   ├── diagnosis-rules.md
│   └── report-format.md
└── scripts/
    ├── calculate_unit_economics.py
    └── test_calculate_unit_economics.py
```

`SKILL.md` contains the shared workflow, routing rules, critical metric boundaries, and authorization limits. Mode selection, metric definitions, calculation schema, diagnosis rules, and report structure live in focused references. The standard-library Python script owns repeatable arithmetic and validation.

The repository `README.md` will list the skill after implementation.

## Operating workflow

1. Read `references/intake.md` and inspect supplied financial, product, sales, cohort, and operating materials before asking questions.
2. Read `references/model-selection.md`. Select one mode, one economic unit, one analysis period, one currency, and one revenue basis. Separate materially different streams rather than averaging incompatible units.
3. Classify each material input as `confirmed`, `reported`, `estimated`, or `unknown`. Do not convert missing price, costs, volume, customers, churn, or capacity to zero.
4. Build a `base` scenario. Add `downside` when a material price, cost, acquisition, retention, or volume assumption is uncertain enough to change a decision. Add `upside` only when useful.
5. Read `references/calculation-model.md`, write the minimum necessary anonymous JSON outside the skill directory, and run `scripts/calculate_unit_economics.py`.
6. Resolve validation errors by correcting the input or retaining an indeterminate result. Do not invent values to produce a complete dashboard.
7. Read `references/diagnosis-rules.md`, connect calculated flags to the evidence and operating constraint, and create sensitivity cases only for variables that can change the decision.
8. Read `references/report-format.md` and produce the report in the user’s language.
9. Obtain explicit authorization immediately before any external communication, price change, campaign change, budget change, contract action, or transaction.

## Data and evidence model

### Money values

Monetary inputs use:

```json
{"amount": 10000, "evidence": "confirmed"}
```

Known amounts are finite and nonnegative. An amount may include an optional `currency`; when present it must match the top-level currency. An unknown amount is:

```json
{"amount": null, "evidence": "unknown"}
```

Numeric zero with `unknown` evidence is invalid. All monetary values in one run use the top-level currency.

### Scalar values

Quantities, rates, periods, and capacities use:

```json
{"value": 120, "evidence": "reported"}
```

Unknown scalars use `null`. Rates are decimals from 0 through 1. Counts and periods are nonnegative; fields used as divisors must be positive for the relevant metric.

### Evidence states

- `confirmed`: supported by a supplied record or directly observable source.
- `reported`: stated by the user without supporting material.
- `estimated`: a forward-looking or modeled assumption.
- `unknown`: missing or unresolved.

The calculator returns `estimate_based: true` when a decision metric depends on an estimated input. It returns `indeterminate` for a metric whose required input is unknown or whose denominator is zero. It must not replace an indeterminate metric with zero.

## Shared driver model

Each scenario contains these unit and period drivers:

- `price_per_unit`;
- `cogs_per_unit`;
- `other_variable_cost_per_unit`;
- `volume_units`;
- `fixed_costs`;
- `new_customers`;
- `units_per_customer_per_period` when payback uses a customer-period contribution;
- optional `capacity_units`;
- acquisition-cost pools by supported CAC basis;
- one LTV model; and
- optional decision targets such as `max_payback_periods`.

The user must define what is included in price, COGS, variable cost, fixed cost, and acquisition cost. Discounts, refunds, credits, payment fees, shipping, usage infrastructure, commissions, delivery labor, support load, and partner revenue share are allocated according to their actual economic behavior. Cost allocation must be internally consistent and must not create duplicate subtraction inside a formula.

The top-level `unit_is_discrete` field distinguishes countable units such as orders, customers, and projects from continuous units such as hours, storage, or usage volume. Customer counts and horizon periods are whole numbers. Economic-unit volume, capacity, and units per customer may be nonnegative decimals when the unit is continuous.

Acquisition pools are analytical views used to calculate CAC and may reuse costs included in the period’s fixed-cost scope. They are not automatically subtracted again from period contribution. The input records whether the selected acquisition pool is already included in `fixed_costs`, and the report explains the scope. Within any single profit formula, a cost must not be counted twice.

### Scenario object

Each scenario follows this structure:

```json
{
  "name": "base",
  "drivers": {
    "price_per_unit": {"amount": 12000, "evidence": "confirmed"},
    "cogs_per_unit": {"amount": 2500, "evidence": "reported"},
    "other_variable_cost_per_unit": {"amount": 1000, "evidence": "estimated"},
    "volume_units": {"value": 180, "evidence": "reported"},
    "fixed_costs": {"amount": 1200000, "evidence": "confirmed"},
    "new_customers": {"value": 30, "evidence": "confirmed"},
    "units_per_customer_per_period": {"value": 1, "evidence": "reported"},
    "capacity_units": {"value": 220, "evidence": "estimated"}
  },
  "acquisition": {
    "decision_cac_basis": "fully_loaded",
    "decision_cac_scope_complete": true,
    "selected_pool_matches_customer_cohort": true,
    "selected_pool_included_in_fixed_costs": true,
    "marginal_new_customers": {"value": 10, "evidence": "estimated"},
    "costs": {
      "paid": {"amount": 240000, "evidence": "confirmed"},
      "blended": {"amount": 420000, "evidence": "reported"},
      "fully_loaded": {"amount": 600000, "evidence": "estimated"}
    }
  },
  "ltv_model": {
    "method": "constant_retention",
    "churn_rate_per_period": {"value": 0.04, "evidence": "estimated"},
    "period_unit": "month"
  },
  "targets": {
    "max_payback_periods": {"value": 8, "evidence": "reported"}
  }
}
```

`capacity_units` and targets are optional. `units_per_customer_per_period` is optional when the selected LTV/payback method does not need it. Acquisition cost keys may be omitted when unavailable, but the selected basis must be present. `marginal_new_customers` is required when a marginal cost pool is supplied and represents incremental customers attributable to the incremental spend; other CAC bases use `drivers.new_customers`. `decision_cac_scope_complete` records whether the selected basis includes every acquisition cost the user considers necessary for the decision. `selected_pool_matches_customer_cohort` records whether the numerator costs and customer denominator represent the same acquisition cohort or a justified lagged attribution. `analysis_period` and every `period_unit` use one of `week`, `month`, `quarter`, or `year` and must match for arithmetic comparisons.

Mode-specific `ltv_model` objects replace the constant-retention fields as follows:

```json
{
  "method": "fixed_horizon",
  "expected_units_per_customer_within_horizon": {"value": 5, "evidence": "estimated"},
  "horizon_periods": {"value": 12, "evidence": "reported"},
  "period_unit": "month"
}
```

```json
{
  "method": "observed_cohort",
  "cohort_customers": {"value": 40, "evidence": "confirmed"},
  "contribution_totals_by_period": [
    {"amount": 320000, "evidence": "confirmed"},
    {"amount": 240000, "evidence": "confirmed"}
  ],
  "period_unit": "month"
}
```

## Core calculations

For each scenario:

```text
revenue = price_per_unit × volume_units
gross_profit_per_unit = price_per_unit − cogs_per_unit
gross_margin = gross_profit_per_unit ÷ price_per_unit
contribution_profit_per_unit
  = price_per_unit − cogs_per_unit − other_variable_cost_per_unit
contribution_margin = contribution_profit_per_unit ÷ price_per_unit
total_contribution_profit = contribution_profit_per_unit × volume_units
contribution_after_fixed_costs = total_contribution_profit − fixed_costs
```

When price is zero, percentage margins are indeterminate while absolute profit remains calculable.

`contribution_after_fixed_costs` is a management-analysis result using the declared fixed-cost scope, not statutory or audited operating profit. Acquisition pools are not subtracted again. The report states whether the selected acquisition pool is already represented in fixed costs.

### Break-even

When `contribution_profit_per_unit > 0`:

```text
break_even_units = fixed_costs ÷ contribution_profit_per_unit
break_even_revenue = fixed_costs ÷ contribution_margin
```

When `unit_is_discrete` is true, also return `break_even_units_ceiling` by rounding up to the next whole deliverable unit. For a continuous unit, return the unrounded `break_even_units` and set the ceiling field to `not_applicable_continuous_unit`.

When contribution is zero or negative, return `no_finite_break_even`. If capacity is known, compare the whole-unit ceiling for a discrete unit and the raw break-even quantity for a continuous unit. Flag `break_even_beyond_capacity` when the applicable requirement exceeds capacity.

### CAC

Supported bases are:

- `paid`: directly attributable paid acquisition spend.
- `blended`: sales and marketing spend for the acquisition cohort or period.
- `fully_loaded`: blended cost plus included acquisition labor, tools, agencies, and allocated acquisition overhead.
- `marginal`: incremental spend divided by incremental new customers for a defined change.

For each supplied non-marginal basis:

```text
cac[basis] = acquisition_costs[basis] ÷ new_customers
```

For marginal CAC:

```text
cac[marginal] = acquisition_costs[marginal] ÷ marginal_new_customers
```

The input selects one `decision_cac_basis` for payback, LTV:CAC, and diagnosis. Other bases remain visible comparisons. If new customers are zero, CAC is indeterminate rather than zero or infinity. The report must show the numerator scope, customer cohort, and timing alignment. A calculated CAC whose scope is incomplete or whose cost/customer cohort is misaligned remains visible but cannot support `profitable_to_scale`.

### Customer contribution and payback

For non-cohort methods:

```text
customer_contribution_per_period
  = contribution_profit_per_unit × units_per_customer_per_period
payback_periods
  = selected_cac ÷ customer_contribution_per_period
```

When contribution is nonpositive, CAC payback is `not_recoverable`. When `units_per_customer_per_period` is unavailable, payback is indeterminate.

For observed cohorts, use cumulative contribution per acquired customer and return the first period in which cumulative contribution equals or exceeds selected CAC. If it does not occur within the observed periods, return `not_observed_within_horizon` without extrapolation.

## LTV methods

Each scenario selects exactly one method.

### `observed_cohort`

Inputs:

- acquired cohort customers;
- ordered contribution totals by period for that cohort; and
- the period unit.

```text
observed_ltv = sum(cohort contribution totals) ÷ cohort customers
```

The result is contribution LTV observed through the last supplied period, not full-lifetime LTV. Cohort customers must be positive. Payback uses cumulative contribution per original acquired customer unless the user supplies a justified surviving-customer denominator for a different analysis.

### `fixed_horizon`

Inputs:

- expected units per customer within the horizon; and
- horizon periods.

```text
fixed_horizon_ltv
  = contribution_profit_per_unit × expected_units_per_customer_within_horizon
```

The output always displays the horizon. This is the normal forecast method for transactional and service-project economics when cohort data is unavailable.

### `constant_retention`

Allowed only for `recurring` mode. Inputs are a positive churn rate measured in the same period as customer contribution.

```text
expected_lifetime_periods = 1 ÷ churn_rate_per_period
estimated_ltv = customer_contribution_per_period ÷ churn_rate_per_period
```

The result assumes a constant churn hazard, stable contribution, no discounting, and no expansion or contraction beyond supplied unit economics. A zero churn rate returns `zero_churn_requires_fixed_horizon_or_cohort`; it never returns infinite LTV.

### LTV:CAC

```text
ltv_to_cac = contribution_ltv ÷ selected_cac
```

If selected CAC is zero, report `not_meaningful_zero_cac` rather than infinity. Do not compare revenue LTV to contribution CAC economics. The report states the LTV method, horizon, CAC basis, cohort, and period alignment beside the ratio.

## Diagnostic rules

The calculator returns flags rather than a universal numeric score. Flags are evaluated from explicit facts and user targets:

- `negative_unit_economics`: contribution profit per unit is zero or negative.
- `acquisition_not_recovered`: selected CAC is not recovered inside the observed or modeled customer horizon.
- `unit_positive_but_cash_hungry`: contribution is positive, but payback exceeds `max_payback_periods` or the credible lifetime/horizon.
- `break_even_beyond_capacity`: required whole units exceed supplied capacity.
- `profitable_to_scale`: contribution is positive, break-even is within known capacity, the selected CAC scope is complete and cohort-aligned, and selected CAC is recoverable within the explicit target or credible horizon.
- `positive_unit_economics_unassessed_acquisition`: contribution is positive but acquisition evidence or target is insufficient to claim scaling support.
- `indeterminate`: required unit economics inputs are unknown.

`profitable_to_scale` means the modeled unit economics support scaling under the stated assumptions. It is not a claim about total cash needs, demand, execution capability, financing, or company value.

No hard-coded LTV:CAC or payback benchmark creates a favorable or unfavorable flag. If the user supplies a policy target, record it as `reported` or `confirmed` and compare against it.

## Sensitivity analysis

Sensitivity cases are explicit named overrides of one source scenario. Each case is recalculated independently and does not stack with another case. Allowed drivers include:

- price per unit;
- COGS per unit;
- other variable cost per unit;
- volume units;
- fixed costs;
- new customers;
- acquisition-cost pools;
- units per customer per period;
- capacity;
- churn;
- fixed-horizon expected units; and
- cohort contribution periods.

Each override carries an evidence state. The calculator returns the recalculated metrics, deltas from the source scenario, and any diagnostic flags added or removed.

Sensitivity cases use explicit field paths and typed replacement values:

```json
"sensitivity_cases": [
  {
    "name": "price-down-and-cogs-up",
    "source_scenario": "base",
    "overrides": {
      "drivers.price_per_unit": {"amount": 10800, "evidence": "estimated"},
      "drivers.cogs_per_unit": {"amount": 3000, "evidence": "estimated"}
    }
  }
]
```

Allowed paths are the driver money/scalar fields, acquisition cost basis entries, `ltv_model` numeric inputs, and target numeric inputs listed in this specification. Structural fields such as mode, currency, unit, evidence keys, method, period unit, scenario name, or CAC basis cannot be changed by sensitivity overrides. A case that needs a structural change is a separate scenario.

The calculator also returns applicable decision breakpoints without inventing target values:

```text
minimum_price_for_positive_contribution
  = cogs_per_unit + other_variable_cost_per_unit

minimum_price_for_break_even_at_current_volume
  = cogs_per_unit + other_variable_cost_per_unit + fixed_costs ÷ volume_units

maximum_variable_cost_for_positive_contribution
  = max(0, price_per_unit − cogs_per_unit)

maximum_cac_for_target_payback
  = customer_contribution_per_period × max_payback_periods

maximum_constant_churn_for_ltv_to_equal_cac
  = customer_contribution_per_period ÷ selected_cac
```

Return a breakpoint only when its denominators and user target are valid. Clamp a churn rate breakpoint above 1 to 1 and explain that the economic constraint is not binding within the valid rate range.

## Script interface

`calculate_unit_economics.py` accepts one JSON path or `-` for standard input and writes compact JSON to standard output. It uses only the Python standard library.

The top-level input contains:

- `mode`;
- `as_of_date`;
- `currency`;
- `analysis_period` such as `month` or `quarter`;
- `unit_name`;
- `unit_is_discrete`;
- `revenue_basis`;
- `scenarios` containing a unique `base` and optional alternatives;
- optional `sensitivity_cases`.

The script must reject:

- malformed JSON or dates;
- unknown modes, LTV methods, CAC bases, or evidence states;
- invalid or missing currency;
- negative or non-finite money, counts, rates, or periods;
- rates outside 0 through 1;
- numeric zero encoded with `unknown` evidence;
- duplicate scenario or sensitivity names;
- sensitivity cases referencing unknown scenarios or unsupported fields;
- a non-recurring mode using constant-retention LTV;
- inconsistent period labels for contribution, churn, cohort, and payback;
- selected CAC bases absent from the acquisition-cost input;
- a marginal acquisition-cost pool without `marginal_new_customers`;
- mixed currencies; and
- hybrid streams combined in one run.

Known zero denominators are not malformed inputs. The script returns a typed indeterminate or not-recoverable metric with a reason instead of raising a division error.

Validation errors go to standard error and return exit status 2. No numerical output is returned after validation failure.

## Output contract

The calculator returns:

- normalized context and evidence summary;
- unit revenue, gross profit, contribution profit, and their margins;
- period totals and contribution after the declared fixed-cost scope;
- break-even units, whole units, revenue, and capacity comparison;
- all supplied CAC bases and the selected basis;
- customer contribution, payback, LTV, LTV method and horizon, and LTV:CAC;
- decision breakpoints;
- diagnostic flags with source facts;
- scenario comparisons to `base`;
- sensitivity results, deltas, and flag changes;
- `estimate_based`, missing inputs, and indeterminate reasons.

The output must distinguish numeric zero, `null`, `no_finite_break_even`, `not_recoverable`, `not_observed_within_horizon`, and `not_meaningful_zero_cac`.

## Report contract

The report is written in the user’s language and presents:

1. decision summary and limits;
2. economic unit, mode, revenue basis, period, and currency;
3. evidence quality and cost-allocation assumptions;
4. gross and contribution economics;
5. CAC by basis and timing alignment;
6. payback, LTV method, horizon, and LTV:CAC;
7. break-even and capacity;
8. base/downside/upside comparison;
9. sensitivity results and decision breakpoints;
10. diagnostic flags and what they do and do not prove;
11. prioritized measurement or operating actions;
12. unknowns, professional-review items, and authorization boundary.

When a metric is indeterminate, the report shows the missing input and next evidence to collect rather than substituting a benchmark. It presents absolute money before percentage ratios when a zero price or small denominator can distort interpretation.

## Safety and authorization

- Collect only the data needed for the economic model. Avoid account numbers, card data, authentication data, personal identifiers, and customer-level personal data.
- Treat cost classification as management-analysis input, not a statutory accounting determination. State allocation assumptions and request qualified review when a legal, tax, labor, or accounting classification materially affects a decision.
- Verify current authoritative sources only when the request depends on current legal, tax, regulatory, financing, or grant facts. Record the access date and source.
- Do not change prices, advertising, budgets, product access, sales compensation, staffing, vendor contracts, or customer terms without explicit authorization immediately before the action.
- Do not contact customers, employees, vendors, platforms, advisers, lenders, or authorities without explicit authorization.

## Testing and acceptance criteria

### Deterministic script tests

`test_calculate_unit_economics.py` must cover at least:

1. recurring positive contribution, CAC, payback, constant-retention LTV, and break-even;
2. zero recurring churn returning a fixed typed reason rather than infinite LTV;
3. transactional negative contribution returning no finite break-even;
4. service-project break-even volume exceeding supplied capacity;
5. observed-cohort LTV and the first observed CAC-payback period;
6. fixed-horizon LTV with an explicit horizon;
7. paid, blended, fully loaded, and marginal CAC remaining distinct;
8. zero new customers returning indeterminate CAC without a division error;
9. zero selected CAC returning a non-meaningful LTV:CAC reason;
10. unknown core input returning `indeterminate` without zero substitution;
11. downside scenario changing acquisition or scaling flags;
12. independent one-variable and multi-variable sensitivity cases;
13. decision breakpoints with valid and invalid denominators;
14. rejection of cross-mode LTV misuse, mixed currencies, malformed evidence, duplicate names, and unsupported sensitivity fields.

Tests assert calculated values, typed states, and invariants rather than report wording.

### Behavioral exercises

Exercise the completed skill with at least three realistic requests:

- a bootstrapped SaaS company with paid and fully loaded CAC, monthly churn, infrastructure cost, and a downside retention case;
- an e-commerce business with refunds, payment fees, shipping, paid acquisition, and repeat orders over a 12-month horizon;
- a service company with direct delivery labor, project capacity, repeat engagements, and uncertain owner-time allocation.

Inspect whether the results select a coherent unit, keep gross and contribution margin separate, avoid infinite LTV, preserve CAC scope, expose infeasible break-even volume, and avoid authorizing external changes.

### Repository validation

Run:

```bash
python3 scripts/validate_skills.py
```

The implementation is complete when the repository validator passes, all deterministic tests pass, the three behavioral exercises produce useful and bounded diagnoses, `README.md` lists the skill, and no scaffold placeholders remain.
