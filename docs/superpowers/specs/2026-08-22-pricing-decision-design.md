# Pricing Decision Design

Date: 2026-08-22  
Status: Accepted for implementation

## Purpose

Create a portable `pricing-decision` skill for bootstrapped and capital-efficient businesses. The skill helps decide whether to raise prices, change packages, change the pricing metric, or change discounts and contract terms. It compares explicit proposals against the current offer, quantifies revenue and contribution impact, assigns segment-level migration policies, and produces a validation plan before any live change.

The skill must answer five operating questions:

1. Which pricing and packaging alternatives are credible for the stated customer value and business model?
2. How does each proposal change revenue, contribution profit, customer count, ARPA, and capacity use under explicit response assumptions?
3. Which existing customer segments migrate, remain on legacy terms, receive a phased transition, or require manual review?
4. Which proposal best supports the user's primary objective without violating stated guardrails?
5. What evidence or limited test is required before rollout?

## Scope

### Included

- Industry-neutral analysis for `recurring`, `transactional`, and `service_project` businesses.
- Four pricing levers: price point, package or plan structure, pricing metric, and discount or contract-period policy.
- `flat`, `base_plus_usage`, `percentage`, and `quoted` charge formulas.
- One currency, analysis period, revenue stream, and usage or capacity unit per run.
- Aggregated customer segments rather than personal customer records.
- Current-plan counterfactual and independently recalculated pricing proposals.
- Existing-customer migration policies: `immediate`, `renewal`, `delayed`, `grandfathered`, `phased`, and `manual_review`.
- Segment-level response assumptions for retention, new-customer volume, usage, and transition discounts.
- Revenue, contribution profit, contribution margin, contribution after fixed costs, ARPA, active customers, price-change burden, and capacity use.
- A user-selected primary objective and optional explicit guardrails.
- Decision statuses: `candidate_for_rollout`, `pilot_first`, `hold_for_evidence`, and `reject_under_assumptions`.
- Independent sensitivity cases with typed override paths.
- A validation plan based on the material uncertainty, without executing the test.
- Deterministic calculations from anonymous JSON using the Python standard library.
- Evidence states `confirmed`, `reported`, `estimated`, and `unknown`.

### Excluded

- Automatically choosing a universally optimal price or assuming a universal acceptable increase.
- Inferring elasticity, willingness to pay, churn, conversion, usage, or competitor response without evidence.
- Personalized pricing based on protected, sensitive, or individually identifying attributes.
- Dynamic pricing, auctions, surge pricing, or real-time price discrimination.
- Tax-inclusive or tax-exclusive legal determinations, regulated-price advice, competition-law conclusions, or contract interpretation.
- Company valuation, market sizing, full cash-runway forecasting, or statutory accounting.
- Publishing prices, changing billing, modifying contracts, contacting customers, or running a live experiment.

## Intended users and requests

The skill applies when a founder or operating team asks whether to raise prices, restructure plans, change a value metric, alter an annual discount, migrate existing customers, or validate a pricing hypothesis.

The discovery description should activate for requests such as:

- “Can we raise prices without losing too much contribution?”
- “Compare these three pricing plans.”
- “Should we grandfather existing customers?”
- “What happens if we move from flat pricing to usage pricing?”
- “Which customers should move at renewal?”
- “Design a safe pricing test.”

It should not activate for a request limited to pricing-page copy, a statutory transfer-pricing analysis, a securities price, or a cash-depletion forecast.

## Approach

The skill is standalone. It may reuse supplied outputs from `unit-economics-diagnostic`, but it must not require another skill to run. The user defines the current offer, customer segments, cost-to-serve model, and candidate proposals in one anonymous input.

The calculator compares a decision-horizon run rate. It does not claim to produce a cumulative rollout cash forecast. Recurring implementation costs and one-time implementation costs remain separately visible. If cumulative timing matters, the report routes the user to a dedicated cash forecast after selecting a candidate rollout schedule.

Each proposal uses explicit response assumptions. The calculator never assumes zero churn, unchanged acquisition, unchanged usage, or unchanged conversion merely because those inputs are missing. An unknown critical response input makes the affected result indeterminate.

## Skill structure

```text
skills/finance/pricing-decision/
├── SKILL.md
├── references/
│   ├── intake.md
│   ├── proposal-design.md
│   ├── calculation-model.md
│   ├── migration-policy.md
│   ├── validation-plan.md
│   └── report-format.md
└── scripts/
    ├── calculate_pricing_decision.py
    └── test_calculate_pricing_decision.py
```

`SKILL.md` holds the shared workflow, important metric boundaries, routing, and authorization limits. References own intake, proposal design, exact JSON and formulas, migration criteria, validation methods, and the report contract. The script owns repeatable validation and arithmetic.

## Operating workflow

1. Read `references/intake.md` and inspect supplied pricing, billing, customer, usage, contribution, churn, loss, and contract materials before asking questions.
2. Select one mode, currency, analysis period, revenue stream, usage unit, and decision horizon. Define the current offer and aggregate segments.
3. Label every material input `confirmed`, `reported`, `estimated`, or `unknown`. Do not replace unknown customer response with zero.
4. Read `references/proposal-design.md`. Define the primary objective and guardrails, then create a small set of materially distinct proposals across the four pricing levers. Do not generate cosmetic alternatives that do not change a decision.
5. Read `references/migration-policy.md`. Assign one migration policy and explicit within-horizon migrated and manual-review shares to each segment. Keep account-level exceptions outside the calculator unless an aggregate strategic-account segment is justified.
6. Read `references/calculation-model.md`, prepare minimum anonymous JSON outside the skill directory, and run `scripts/calculate_pricing_decision.py`.
7. Resolve validation errors by correcting inputs. Keep an indeterminate result when evidence is unavailable; do not invent elasticity or retention.
8. Review proposal status, guardrails, segment burden, and sensitivities. Read `references/validation-plan.md` and design the minimum useful evidence-gathering step for the decisive unknown.
9. Read `references/report-format.md` and produce the report in the user's language.
10. Obtain explicit authorization immediately before any customer contact, public price change, billing change, contract action, campaign, experiment, or transaction.

## Evidence and value model

### Money values

```json
{"amount": 10000, "evidence": "confirmed"}
```

Known monetary values are finite and nonnegative. They may include an optional `currency` equal to the top-level currency. Unknown money is:

```json
{"amount": null, "evidence": "unknown"}
```

### Scalar values

```json
{"value": 120, "evidence": "reported"}
```

Unknown scalars use `null`. Rates and shares are from 0 through 1. Counts are nonnegative and customer counts are whole numbers. Multipliers and usage quantities are nonnegative.

### Evidence states

- `confirmed`: supported by a supplied record or direct observation.
- `reported`: stated by the user without supporting material.
- `estimated`: a forward-looking, allocated, or modeled assumption.
- `unknown`: missing or unresolved.

The calculator returns `estimate_based` and `missing_inputs`. It returns typed non-calculable states instead of converting unknowns to zero.

## Top-level model

```json
{
  "mode": "recurring",
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "analysis_period": "month",
  "evaluation_horizon_periods": {"value": 12, "evidence": "reported"},
  "usage_unit_name": "active seat",
  "objective": {"metric": "contribution_after_fixed_costs"},
  "guardrails": {
    "max_active_customer_loss_rate": {"value": 0.05, "evidence": "reported"},
    "min_contribution_margin": {"value": 0.55, "evidence": "reported"},
    "max_weighted_average_price_increase_rate": {"value": 0.25, "evidence": "reported"},
    "max_manual_review_share": {"value": 0.10, "evidence": "reported"},
    "capacity_units_per_period": {"value": 4000, "evidence": "reported"}
  },
  "current_fixed_costs_per_period": {"amount": 3000000, "evidence": "reported"},
  "plans": [],
  "segments": [],
  "proposals": [],
  "sensitivity_cases": []
}
```

Supported objective metrics are `revenue`, `contribution_profit`, `contribution_after_fixed_costs`, `arpa`, and `active_customers`. The calculator does not silently default to revenue maximization. When the objective is omitted, it compares metrics without granting a favorable rollout status.

Guardrails are optional and user supplied. No universal churn, price-increase, margin, or conversion threshold is hard-coded. An unknown guardrail cannot be treated as passed.

## Plans and charge formulas

Every plan has a unique `name`, a short `package_label`, and exactly one pricing formula.

### `flat`

```json
{
  "name": "standard-current",
  "package_label": "Standard",
  "pricing": {
    "model": "flat",
    "flat_fee": {"amount": 20000, "evidence": "confirmed"}
  }
}
```

`charge = flat_fee`.

### `base_plus_usage`

```json
{
  "name": "standard-usage",
  "package_label": "Standard",
  "pricing": {
    "model": "base_plus_usage",
    "base_fee": {"amount": 10000, "evidence": "estimated"},
    "included_usage_units": {"value": 5, "evidence": "estimated"},
    "price_per_excess_unit": {"amount": 2000, "evidence": "estimated"},
    "minimum_fee": {"amount": 10000, "evidence": "estimated"},
    "maximum_fee": {"amount": null, "evidence": "unknown"}
  }
}
```

The maximum fee may be omitted. If present and unknown, the charge is indeterminate because the plan explicitly depends on an unresolved cap. Otherwise:

```text
raw_charge = base_fee + max(0, usage - included_usage) × excess_unit_price
charge = min(max(raw_charge, minimum_fee), maximum_fee when supplied)
```

### `percentage`

```json
{
  "name": "transaction-rate",
  "package_label": "Transaction",
  "pricing": {
    "model": "percentage",
    "percentage_rate": {"value": 0.025, "evidence": "estimated"},
    "minimum_fee": {"amount": 5000, "evidence": "estimated"}
  }
}
```

`raw_charge = billable_amount_per_customer_per_period × percentage_rate`, followed by optional minimum and maximum fees. `billable_amount` is the contractually relevant base, not automatically GMV or company revenue.

### `quoted`

```json
{
  "name": "enterprise-quoted",
  "package_label": "Enterprise",
  "pricing": {"model": "quoted"}
}
```

Each assignment to this plan must supply `quoted_charge_per_customer_per_period`. The calculator does not invent a quote.

Package contents and qualitative value changes are recorded in the analysis and report but are not assigned arbitrary monetary value by the script.

## Customer segments

Segments are anonymous, mutually exclusive aggregates.

```json
{
  "name": "small-teams",
  "current_plan": "standard-current",
  "current_customers": {"value": 120, "evidence": "confirmed"},
  "baseline_retention_rate": {"value": 0.96, "evidence": "reported"},
  "baseline_new_customers_per_period": {"value": 12, "evidence": "reported"},
  "usage_units_per_customer_per_period": {"value": 4, "evidence": "reported"},
  "billable_amount_per_customer_per_period": {"amount": 0, "evidence": "confirmed"},
  "current_quoted_charge_per_customer_per_period": {"amount": 0, "evidence": "confirmed"},
  "fixed_variable_cost_per_customer_per_period": {"amount": 2500, "evidence": "reported"},
  "variable_cost_per_usage_unit": {"amount": 700, "evidence": "reported"}
}
```

`billable_amount_per_customer_per_period` is required only by percentage pricing. `current_quoted_charge_per_customer_per_period` is required only when the current plan uses quoted pricing. A confirmed zero is valid when a field is present but not economically applicable. Cost to serve is:

```text
cost_per_customer
  = fixed_variable_cost_per_customer_per_period
  + variable_cost_per_usage_unit × usage_units_per_customer_per_period
```

Service-project direct labor and contractors belong in this cost model when attributable to the unit. Marketplace charge formulas use the defined contractual billable base and must not silently treat GMV as company revenue.

## Current counterfactual

For each segment:

```text
baseline_retained_existing = current_customers × baseline_retention_rate
baseline_new_customers = baseline_new_customers_per_period
baseline_active_customers = retained_existing + new_customers
baseline_charge = charge(current_plan, baseline usage and billable amount)
baseline_revenue = baseline_active_customers × baseline_charge
baseline_contribution
  = baseline_revenue - baseline_active_customers × baseline_cost_per_customer
```

Customer counts may become expected decimal values after applying rates. Input customer counts remain whole numbers; outputs are modeled expectations.

## Pricing proposals and assignments

Each proposal has a unique name, a validation stage, costs, and exactly one assignment for every segment.

```json
{
  "name": "usage-pricing",
  "validation_stage": "hypothesis",
  "change_summary": ["Lower base fee", "Add active-seat metric"],
  "incremental_fixed_costs_per_period": {"amount": 150000, "evidence": "estimated"},
  "one_time_implementation_costs": {"amount": 600000, "evidence": "estimated"},
  "assignments": [
    {
      "segment": "small-teams",
      "target_plan": "standard-usage",
      "migration_policy": "renewal",
      "migration_share_within_horizon": {"value": 0.75, "evidence": "estimated"},
      "manual_review_share": {"value": 0, "evidence": "confirmed"},
      "retention_rate_after_migration": {"value": 0.92, "evidence": "estimated"},
      "new_customer_multiplier": {"value": 1.05, "evidence": "estimated"},
      "usage_multiplier": {"value": 1, "evidence": "reported"},
      "billable_amount_multiplier": {"value": 1, "evidence": "reported"},
      "variable_cost_multiplier": {"value": 1, "evidence": "reported"},
      "transition_discount_rate": {"value": 0.10, "evidence": "estimated"}
    }
  ]
}
```

Supported validation stages are `hypothesis`, `piloted`, and `validated`. The stage is evidence about rollout readiness, not a financial input.

For each assignment, `migration_share_within_horizon + manual_review_share` must not exceed 1. `grandfathered` requires a zero migration share. `manual_review` requires a positive manual-review share. Other policies use explicit shares rather than inferred contract timing.

The assignment may supply `quoted_charge_per_customer_per_period` when the target plan uses quoted pricing.

## Proposal calculations

For each segment:

```text
migration_cohort = current_customers × migration_share
manual_review_customers = current_customers × manual_review_share
migrated_retained = migration_cohort × retention_rate_after_migration
migration_losses = migration_cohort × (1 - retention_rate_after_migration)
legacy_population = current_customers - migration_cohort
legacy_retained = legacy_population × baseline_retention_rate
proposal_new_customers
  = baseline_new_customers_per_period × new_customer_multiplier
proposal_active_customers
  = migrated_retained + legacy_retained + proposal_new_customers
```

Manual-review customers remain on legacy pricing in the financial run rate until a separate explicit proposal assigns their outcome. They are also displayed as unresolved manual-review load.

```text
proposal_usage = baseline usage × usage_multiplier
target_charge = charge(target_plan, proposal usage, proposal billable amount)
migrated_charge = target_charge × (1 - transition_discount_rate)
legacy_revenue = legacy_retained × current_charge
migrated_revenue = migrated_retained × migrated_charge
new_revenue = proposal_new_customers × target_charge
proposal_revenue = legacy_revenue + migrated_revenue + new_revenue
proposal_cost_per_customer = baseline cost model at proposal usage × variable_cost_multiplier
proposal_contribution = proposal_revenue - total variable cost
proposal_contribution_after_fixed_costs
  = proposal_contribution
  - current_fixed_costs_per_period
  - incremental_fixed_costs_per_period
```

One-time implementation costs remain separate from run-rate contribution. The calculator must not multiply endpoint run-rate improvement by the evaluation horizon and call it realized cash benefit.

Additional outputs include:

- active-customer delta and loss rate versus current counterfactual;
- revenue and contribution deltas;
- contribution margin;
- ARPA and ARPA delta;
- usage and optional capacity status;
- migrated, legacy, migration-loss, new, and manual-review customer expectations;
- segment current charge, effective migrated charge, target new-customer charge, absolute change, and rate change;
- weighted average and weighted median price increase among migrated retained customers;
- counts and shares in price-change bands: decrease, unchanged, `0–10%`, `10–25%`, `25–50%`, and `over-50%`.

When the current charge is zero, the percentage increase is `not_meaningful_zero_current_price`; absolute change remains visible.

## Capacity

When `capacity_units_per_period` is supplied:

```text
total_usage = sum(proposal active customers × proposal usage per customer)
capacity_status = within_capacity if total_usage <= capacity else beyond_capacity
```

An unknown capacity produces `unassessed`, not a passed guardrail. Capacity represents the declared usage or delivery unit. If operational capacity uses another unit, run a separate operational analysis rather than mixing units.

## Objectives and guardrails

The current counterfactual is the reference for every proposal. Objective deltas are calculated only when both proposal and current values are numeric.

Supported guardrail checks are:

- maximum active-customer loss rate;
- minimum contribution margin;
- maximum weighted-average migrated price increase;
- maximum manual-review share; and
- declared capacity.

Each check returns `passed`, `violated`, or `unassessed`. The output lists each violation and missing condition. No threshold exists unless the user supplies it.

## Decision status

The calculator returns one status per proposal:

- `hold_for_evidence`: the primary objective, a required charge, a critical response assumption, or a supplied guardrail is indeterminate.
- `reject_under_assumptions`: the primary objective does not improve, or at least one supplied guardrail is violated.
- `candidate_for_rollout`: the objective improves, every supplied guardrail passes, capacity is within bounds when supplied, and `validation_stage` is `validated`.
- `pilot_first`: the objective improves and no supplied guardrail is violated, but the proposal is `hypothesis` or `piloted` rather than validated.

Statuses are decision aids, not permission to change pricing. If no primary objective is supplied, financially complete proposals remain `hold_for_evidence` with reason `objective_not_selected`.

## Sensitivity analysis

Sensitivity cases are explicit overrides of one proposal and are recalculated independently from the same current counterfactual.

```json
{
  "name": "higher-migration-churn",
  "source_proposal": "usage-pricing",
  "overrides": {
    "assignments.small-teams.retention_rate_after_migration": {
      "value": 0.85,
      "evidence": "estimated"
    }
  }
}
```

Allowed paths are proposal cost values and assignment response values: migration share, manual-review share, retention, new-customer multiplier, usage multiplier, billable-amount multiplier, variable-cost multiplier, transition discount, and quoted charge. Structural fields such as mode, plan formula, target plan, migration policy, validation stage, objective, guardrails, segment identity, or currency cannot be overridden.

Each case returns recalculated metrics, numeric deltas from its source proposal, and added or removed violations and decision reasons. Cases never stack.

## Typed non-calculable states and validation

Stable output states include:

- `indeterminate`: a required input is unknown;
- `not_meaningful_zero_current_price`: a percentage price change has a confirmed zero denominator;
- `not_applicable`: a metric does not apply to the charge model or selected objective;
- `unassessed`: an optional guardrail such as capacity cannot be evaluated;
- `objective_not_selected`: no primary decision objective was supplied.

The script rejects malformed dates, currencies, evidence wrappers, negative values, shares outside 0 through 1, invalid plan formulas, missing segment assignments, unknown plan or segment references, duplicate names, fractional input customer counts, inconsistent migration shares, incompatible policy shares, quoted pricing without a quote, unknown sensitivity sources, unsupported override paths, and mixed currencies.

Known zero denominators return a typed result rather than validation failure or infinity. Validation errors go to standard error and return exit status 2 without partial numeric output.

## Validation-plan design

The calculator identifies decisive unknowns and estimated assumptions. The agent selects the least costly credible validation method from:

- historical quote, loss, renewal, discount, and usage analysis;
- customer value or willingness-to-pay interviews;
- structured willingness-to-pay survey when sample quality supports it;
- nonbinding sales quote or offer testing for new prospects;
- new-customer-only controlled test where lawful and operationally appropriate;
- renewal-cohort pilot;
- phased rollout with explicit rollback and support capacity.

The plan includes hypothesis, target segment, primary metric, guardrails, duration, sample rationale, stopping conditions, decision rule, dependencies, owner, and authorization checkpoint. It must not fabricate statistical power from an unavailable baseline. Small bootstrapped samples may use sequential evidence and explicit uncertainty rather than a false precision claim.

## Report contract

The report uses this heading order:

1. Decision summary
2. Current model and evidence quality
3. Primary objective and guardrails
4. Proposal comparison
5. Segment financial impact
6. Existing-customer migration policy
7. Price-burden distribution and exceptions
8. Sensitivity and decision breakpoints
9. Validation plan
10. Rollout prerequisites and authorization boundary
11. Unknowns and next evidence

The report shows current versus proposal definitions, charge formula, package changes, metric changes, discounts, revenue and contribution scope, migration horizon, response assumptions, evidence labels, proposal status, and reasons. It keeps run-rate impact separate from one-time implementation costs and from cumulative cash impact.

## Authorization and professional boundaries

The skill may analyze, draft alternatives, and prepare a validation or migration plan. It does not authorize publishing a price, editing a billing system, changing a contract, changing an invoice, changing an advertisement, contacting a customer, starting an experiment, or making a transaction.

Obtain explicit user authorization immediately before each external or production mutation. When consumer-protection, competition, regulated-price, tax, contract, or notice-period facts materially affect the decision, verify current authoritative sources or route to an appropriate professional. Do not claim professional legal, tax, or accounting conclusions.

## Behavioral verification

Exercise the completed skill with at least three realistic cases:

1. A recurring SaaS proposal that changes flat plans to base-plus-usage, includes a renewal migration, a grandfathered segment, and unknown downside retention.
2. A transactional or e-commerce proposal that changes a flat transaction fee to a percentage or hybrid formula and preserves the distinction between billable base and company revenue.
3. A service-project proposal with quoted or flat project fees, direct delivery cost, a phased migration, strategic manual review, and a capacity violation.

The calculator test suite covers all charge models, evidence wrappers, baseline arithmetic, migration arithmetic, price-change bands, objectives, guardrails, statuses, zero current price, unknown response assumptions, policy validation, independent sensitivity, and CLI behavior. Repository validation and placeholder scans must also pass.
