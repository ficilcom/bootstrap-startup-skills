# Pricing Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable industry-neutral skill that compares pricing and packaging proposals, quantifies segment-level financial and migration impact, applies user-defined objectives and guardrails, and produces a validation plan without executing a live price change.

**Architecture:** A concise `SKILL.md` routes an agent to focused intake, proposal, calculation, migration, validation, and report references. A standard-library Python module validates anonymous JSON, calculates the current counterfactual once, independently recalculates every proposal and sensitivity case, and returns typed decision states; a standard-library `unittest` suite verifies formulas and behavioral boundaries.

**Tech Stack:** Markdown, Python 3 standard library, JSON, `decimal.Decimal`, `unittest`

**Spec:** `docs/superpowers/specs/2026-08-22-pricing-decision-design.md`

## Global Constraints

- Create the public skill at `skills/finance/pricing-decision/` with matching lowercase, hyphenated frontmatter name.
- Use only the Python standard library.
- Support `recurring`, `transactional`, and `service_project` without combining unlike streams in one run.
- Support `flat`, `base_plus_usage`, `percentage`, and `quoted` pricing models.
- Analyze one currency, period unit, revenue stream, and usage or capacity unit per run.
- Use aggregate customer segments; do not require personal or protected customer attributes.
- Represent money as `{amount, evidence}` and scalars as `{value, evidence}`; `unknown` always carries JSON `null`, never numeric zero.
- Do not infer elasticity, retention, conversion, new-customer volume, usage response, or willingness to pay from missing data.
- Keep decision-horizon run rate, recurring fixed costs, and one-time implementation costs separate.
- Do not silently optimize revenue when the user has not selected a primary objective.
- Do not hard-code a favorable price increase, churn, contribution-margin, or conversion benchmark.
- Recalculate every proposal and sensitivity case independently from the current counterfactual.
- Do not authorize price publication, billing changes, contract changes, customer messages, campaigns, experiments, or transactions.

---

### Task 1: Typed input validation and charge formulas

**Files:**
- Create: `skills/finance/pricing-decision/scripts/calculate_pricing_decision.py`
- Create: `skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

**Interfaces:**
- Consumes: JSON-compatible `dict[str, object]` with plans, segments, proposals, objectives, and guardrails from the specification.
- Produces: `validate(payload: object) -> dict[str, object]`, `money_value(entry: object, path: str, currency: str) -> Decimal | None`, `scalar_value(entry: object, path: str, *, rate: bool = False, integer: bool = False) -> Decimal | None`, and `calculate_charge(plan: dict[str, object], *, usage: Decimal | None, billable_amount: Decimal | None, quoted_charge: Decimal | None, currency: str) -> Decimal | str`.

- [ ] **Step 1: Write a complete recurring fixture and failing validation tests**

Create helpers `money()`, `scalar()`, and `recurring_payload()`. The fixture uses one current flat plan at JPY 20,000, one proposed flat plan at JPY 25,000, 100 current customers, 95% baseline retention, 10 baseline new customers, usage 8, JPY 2,000 fixed variable cost, JPY 500 per usage unit, JPY 1,000,000 current fixed costs, and one proposal named `higher-flat-price` with `hypothesis` validation stage. Its `renewal` assignment migrates 80%, sends 10% to manual review, assumes 90% migration retention, 1.1 times new customers, unchanged usage and cost, and a 10% transition discount. The proposal adds JPY 100,000 recurring fixed cost and JPY 600,000 one-time cost.

Set the fixture objective to `contribution_after_fixed_costs`. Supply permissive explicit guardrails that the base proposal passes: maximum active-customer loss 5%, minimum contribution margin 60%, maximum weighted-average price increase 25%, maximum manual-review share 15%, and capacity 1,000 usage units per period. These are fixture values, not skill defaults.

Add focused tests including:

```python
def test_rejects_unknown_money_encoded_as_zero(self):
    payload = recurring_payload()
    payload["plans"][0]["pricing"]["flat_fee"] = money(0, "unknown")
    with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
        calculate(payload)

def test_rejects_migration_and_review_shares_above_one(self):
    payload = recurring_payload()
    assignment = payload["proposals"][0]["assignments"][0]
    assignment["migration_share_within_horizon"] = scalar(0.8)
    assignment["manual_review_share"] = scalar(0.3)
    with self.assertRaisesRegex(ValueError, "migration and manual-review shares"):
        calculate(payload)
```

Also test malformed dates and currency, mixed optional money currency, negative numbers, rates above 1, fractional input customer counts, duplicate plan/segment/proposal names, unknown plan references, missing segment assignments, duplicate assignments, `grandfathered` with nonzero migration, `manual_review` with zero review share, an invalid objective, quoted current pricing without a current quote, quoted target pricing without an assignment quote, and a constant field supplied to the wrong formula.

- [ ] **Step 2: Run the test file and confirm the import failure**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: `ModuleNotFoundError` because `calculate_pricing_decision.py` does not exist.

- [ ] **Step 3: Implement evidence wrappers and structural validation**

Define:

```python
EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"recurring", "transactional", "service_project"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
PRICING_MODELS = {"flat", "base_plus_usage", "percentage", "quoted"}
MIGRATION_POLICIES = {
    "immediate", "renewal", "delayed", "grandfathered", "phased", "manual_review"
}
VALIDATION_STAGES = {"hypothesis", "piloted", "validated"}
OBJECTIVE_METRICS = {
    "revenue", "contribution_profit", "contribution_after_fixed_costs", "arpa",
    "active_customers"
}
```

Validate exact required top-level fields, ISO date, three-letter currency, analysis period, evidence wrappers, formula-specific plan fields, unique names, segment fields, current-plan references, objective shape, supported guardrails, proposal costs, and one assignment per segment. Known values are finite and nonnegative. Customer counts and horizon periods are whole numbers. Rates and shares are from 0 through 1.

Cross-validate each assignment:

```python
if migration_share + manual_review_share > 1:
    raise ValueError("migration and manual-review shares must sum to at most 1")
if policy == "grandfathered" and migration_share != 0:
    raise ValueError("grandfathered requires zero migration share")
if policy == "manual_review" and manual_review_share == 0:
    raise ValueError("manual_review requires a positive manual-review share")
```

Require `current_quoted_charge_per_customer_per_period` for a segment on a quoted current plan and `quoted_charge_per_customer_per_period` for an assignment targeting a quoted plan.

- [ ] **Step 4: Add failing charge-formula tests**

Cover the four formulas and optional bounds:

```python
def test_base_plus_usage_applies_included_units_and_bounds(self):
    plan = usage_plan(base=10_000, included=5, excess=2_000, minimum=10_000, maximum=20_000)
    self.assertEqual(calculate_charge(plan, usage=Decimal("8"), billable_amount=None,
                                      quoted_charge=None, currency="JPY"), 16_000)
    self.assertEqual(calculate_charge(plan, usage=Decimal("20"), billable_amount=None,
                                      quoted_charge=None, currency="JPY"), 20_000)

def test_percentage_uses_declared_billable_base(self):
    plan = percentage_plan(rate=0.025, minimum=5_000)
    result = calculate_charge(plan, usage=None, billable_amount=Decimal("400000"),
                              quoted_charge=None, currency="JPY")
    self.assertEqual(result, 10_000)
```

Also assert flat charges, quoted charges, missing required usage or billable amount returning `indeterminate`, and an explicitly unknown fee cap making the charge indeterminate rather than uncapped.

- [ ] **Step 5: Implement deterministic charge calculation**

Use `Decimal` throughout. For base-plus-usage:

```python
excess = max(Decimal("0"), usage - included_usage)
raw_charge = base_fee + excess * price_per_excess_unit
charge = max(raw_charge, minimum_fee) if minimum_fee is not None else raw_charge
charge = min(charge, maximum_fee) if maximum_fee is not None else charge
```

Distinguish an omitted cap from a supplied `{amount: null, evidence: "unknown"}` cap. For percentage pricing, multiply the declared billable amount by the rate before applying bounds. For quoted pricing, require the applicable segment or assignment quote. Return `indeterminate` when a required economic value is unknown.

- [ ] **Step 6: Run Task 1 tests**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: all validation and charge-formula tests pass.

- [ ] **Step 7: Commit validation and charge formulas**

```bash
git add skills/finance/pricing-decision/scripts
git commit -m "feat: validate pricing decision inputs"
```

---

### Task 2: Current counterfactual and proposal financials

**Files:**
- Modify: `skills/finance/pricing-decision/scripts/calculate_pricing_decision.py`
- Modify: `skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

**Interfaces:**
- Consumes: validated plans, aggregate segments, current fixed costs, proposal costs, and proposal assignments.
- Produces: `calculate_current(data: dict[str, object]) -> dict[str, object]`, `calculate_proposal(data: dict[str, object], proposal: dict[str, object], current: dict[str, object]) -> dict[str, object]`, and `calculate(payload: dict[str, object]) -> dict[str, object]` with top-level `current`, `proposals`, and `sensitivity_cases`.

- [ ] **Step 1: Add failing current-counterfactual tests**

Using `recurring_payload()`, assert:

```python
current = calculate(recurring_payload())["current"]
self.assertEqual(current["metrics"]["active_customers"], 105)
self.assertEqual(current["metrics"]["revenue"], 2_100_000)
self.assertEqual(current["metrics"]["contribution_profit"], 1_470_000)
self.assertEqual(current["metrics"]["contribution_after_fixed_costs"], 470_000)
self.assertEqual(current["metrics"]["arpa"], 20_000)
self.assertEqual(current["metrics"]["total_usage_units"], 840)
```

Add tests for a percentage current plan, a quoted current plan, a confirmed zero current price, and unknown baseline retention causing affected totals to remain `indeterminate` with `missing_inputs`.

- [ ] **Step 2: Run tests and confirm current metrics are absent**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: failures show that `current` and its metric fields are missing.

- [ ] **Step 3: Implement segment current economics and aggregation**

For every segment calculate:

```python
retained = current_customers * baseline_retention_rate
new_customers = baseline_new_customers_per_period
active = retained + new_customers
cost_per_customer = fixed_variable_cost + variable_cost_per_usage_unit * usage
revenue = active * current_charge
contribution = revenue - active * cost_per_customer
```

Aggregate numeric values only when every required segment value is known. Return partial segment results plus top-level `indeterminate` metrics and exact `missing_inputs` when a required value is unknown. Calculate contribution margin only for positive nonzero revenue; return `indeterminate_zero_revenue` at confirmed zero revenue. Compare total usage with supplied capacity and return `within_capacity`, `beyond_capacity`, or `unassessed`.

- [ ] **Step 4: Add failing migration and proposal tests**

The fixture proposal migrates 80% of the segment, places 10% in manual review, retains 90% of the migration cohort, applies a 10% transition discount to the JPY 25,000 target price, expects 1.1 times new customers, preserves usage, adds JPY 100,000 recurring fixed costs, and records JPY 600,000 one-time costs.

Assert:

```python
proposal = calculate(recurring_payload())["proposals"][0]
segment = proposal["segments"][0]
self.assertEqual(segment["migration_cohort"], 80)
self.assertEqual(segment["migrated_retained_customers"], 72)
self.assertEqual(segment["migration_losses"], 8)
self.assertEqual(segment["legacy_retained_customers"], 19)
self.assertEqual(segment["new_customers"], 11)
self.assertEqual(segment["manual_review_customers"], 10)
self.assertEqual(segment["effective_migrated_charge"], 22_500)
self.assertEqual(proposal["metrics"]["active_customers"], 102)
self.assertEqual(proposal["metrics"]["revenue"], 2_275_000)
self.assertEqual(proposal["metrics"]["contribution_profit"], 1_663_000)
self.assertEqual(proposal["metrics"]["contribution_after_fixed_costs"], 563_000)
self.assertEqual(proposal["deltas"]["contribution_after_fixed_costs"], 93_000)
self.assertEqual(proposal["one_time_implementation_costs"], 600_000)
```

Also test `grandfathered` financial treatment, a phased partial migration, a quoted target, usage and variable-cost multipliers, a transition discount applying only to migrated existing customers, and unknown migration retention causing proposal metrics to be indeterminate rather than assuming no losses.

- [ ] **Step 5: Implement proposal recalculation**

Use the exact formulas from the specification:

```python
migration_cohort = current_customers * migration_share
migrated_retained = migration_cohort * migration_retention
migration_losses = migration_cohort * (Decimal("1") - migration_retention)
legacy_retained = (current_customers - migration_cohort) * baseline_retention
new_customers = baseline_new_customers * new_customer_multiplier
active = migrated_retained + legacy_retained + new_customers
```

Calculate legacy revenue at the current charge, migrated revenue at the target charge after transition discount, and new-customer revenue at the undiscounted target charge. Apply proposal usage to the baseline cost formula, then the assignment variable-cost multiplier. Subtract current and incremental fixed costs once. Keep one-time implementation costs outside run-rate metrics.

Return numeric deltas for revenue, contribution, contribution after fixed costs, active customers, ARPA, and usage only when both proposal and current values are numeric.

- [ ] **Step 6: Run Task 2 tests**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: validation, charge, current, and proposal tests pass.

- [ ] **Step 7: Commit financial and migration calculations**

```bash
git add skills/finance/pricing-decision/scripts
git commit -m "feat: calculate pricing proposal impact"
```

---

### Task 3: Price burden, guardrails, and decision status

**Files:**
- Modify: `skills/finance/pricing-decision/scripts/calculate_pricing_decision.py`
- Modify: `skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

**Interfaces:**
- Consumes: current and proposal metrics, migrated segment charges, user objective, optional guardrails, capacity, and proposal validation stage.
- Produces: `calculate_price_burden(segments: list[dict[str, object]]) -> dict[str, object]`, `evaluate_guardrails(data: dict[str, object], proposal_result: dict[str, object]) -> dict[str, object]`, and `assign_decision_status(data: dict[str, object], proposal: dict[str, object], result: dict[str, object]) -> tuple[str, list[str]]`.

- [ ] **Step 1: Add failing price-burden tests**

The recurring fixture migrates 72 retained customers from JPY 20,000 to an effective JPY 22,500 charge. Assert:

```python
burden = calculate(recurring_payload())["proposals"][0]["price_burden"]
self.assertEqual(burden["weighted_average_increase_rate"], Decimal("0.125"))
self.assertEqual(burden["weighted_median_increase_rate"], Decimal("0.125"))
self.assertEqual(burden["bands"]["10_to_25_percent"]["customers"], 72)
```

Add multiple segments spanning decrease, unchanged, 0–10%, 10–25%, 25–50%, and over-50% bands. Add a zero-current-price segment and assert that its rate is `not_meaningful_zero_current_price` while its absolute increase remains numeric and it is excluded from weighted percentage metrics with an explicit excluded-customer count.

- [ ] **Step 2: Implement weighted burden calculation**

Use migrated retained customer expectations as weights. Calculate weighted mean and a deterministic weighted median by sorting numeric rates and taking the first rate whose cumulative weight reaches at least half the total included weight. Return per-band customer counts and shares. Do not mix new-customer charges into existing-customer migration burden.

- [ ] **Step 3: Add failing objective and guardrail tests**

Cover these cases:

```python
def test_hypothesis_with_improving_objective_requires_pilot(self):
    result = calculate(recurring_payload())["proposals"][0]
    self.assertEqual(result["objective"]["delta"], 93_000)
    self.assertEqual(result["decision_status"], "pilot_first")

def test_validated_proposal_with_passing_guardrails_is_candidate(self):
    payload = recurring_payload()
    payload["proposals"][0]["validation_stage"] = "validated"
    result = calculate(payload)["proposals"][0]
    self.assertEqual(result["decision_status"], "candidate_for_rollout")

def test_price_increase_guardrail_can_reject_improving_proposal(self):
    payload = recurring_payload()
    payload["guardrails"]["max_weighted_average_price_increase_rate"] = scalar(0.10)
    result = calculate(payload)["proposals"][0]
    self.assertEqual(result["guardrails"]["max_weighted_average_price_increase_rate"], "violated")
    self.assertEqual(result["decision_status"], "reject_under_assumptions")
```

Also test minimum contribution margin, maximum active-customer loss rate, maximum manual-review share, capacity violation, objective decrease, unknown objective metric, a supplied but unknown guardrail, no objective selected, and unknown critical retention. Verify that no universal threshold is applied when a guardrail is omitted.

- [ ] **Step 4: Implement objective and guardrail evaluation**

Return the selected metric, current value, proposal value, and delta. Active-customer loss rate is:

```python
loss_rate = max(Decimal("0"), current_active - proposal_active) / current_active
```

At confirmed zero current active customers, return `not_meaningful_zero_current_customers`. Manual-review share uses total current customers as denominator. Every supplied check returns `passed`, `violated`, or `unassessed`, plus current value and threshold. Capacity uses the proposal's existing capacity status.

- [ ] **Step 5: Implement four decision statuses**

Apply this precedence:

```python
if objective_missing_or_indeterminate or any_supplied_guardrail_unassessed or critical_inputs_missing:
    status = "hold_for_evidence"
elif objective_delta <= 0 or any_guardrail_violated:
    status = "reject_under_assumptions"
elif proposal["validation_stage"] == "validated":
    status = "candidate_for_rollout"
else:
    status = "pilot_first"
```

Return stable reasons such as `objective_not_selected`, `objective_indeterminate`, `critical_response_unknown`, `guardrail_unassessed:<name>`, `objective_not_improved`, `guardrail_violated:<name>`, and `validation_required`. A favorable status never authorizes rollout.

- [ ] **Step 6: Run Task 3 tests**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: all price-burden, objective, guardrail, and decision tests pass with earlier tests.

- [ ] **Step 7: Commit decision logic**

```bash
git add skills/finance/pricing-decision/scripts
git commit -m "feat: evaluate pricing decision guardrails"
```

---

### Task 4: Independent sensitivity, comparisons, and CLI

**Files:**
- Modify: `skills/finance/pricing-decision/scripts/calculate_pricing_decision.py`
- Modify: `skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

**Interfaces:**
- Consumes: validated `sensitivity_cases` containing `name`, `source_proposal`, and supported typed overrides.
- Produces: `_apply_overrides(source: dict[str, object], overrides: dict[str, object]) -> dict[str, object]`, `_compare_results(result: dict[str, object], source: dict[str, object]) -> dict[str, object]`, top-level `sensitivity_cases`, and CLI `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Add failing sensitivity validation tests**

Use assignment paths keyed by aggregate segment name:

```python
payload["sensitivity_cases"] = [{
    "name": "retention-downside",
    "source_proposal": "higher-flat-price",
    "overrides": {
        "assignments.small-teams.retention_rate_after_migration":
            scalar(0.82, "estimated")
    }
}]
```

Test duplicate sensitivity names, unknown source proposals, unknown segment names, unsupported structural paths such as `validation_stage`, `target_plan`, `migration_policy`, `plans`, or `objective`, untyped replacement values, and a replacement that makes migration plus manual-review shares exceed 1.

- [ ] **Step 2: Implement allowed-path validation and deep-copy overrides**

Allow only:

```text
incremental_fixed_costs_per_period
one_time_implementation_costs
assignments.<segment>.migration_share_within_horizon
assignments.<segment>.manual_review_share
assignments.<segment>.retention_rate_after_migration
assignments.<segment>.new_customer_multiplier
assignments.<segment>.usage_multiplier
assignments.<segment>.billable_amount_multiplier
assignments.<segment>.variable_cost_multiplier
assignments.<segment>.transition_discount_rate
assignments.<segment>.quoted_charge_per_customer_per_period
```

Deep-copy the source proposal, index assignments by their `segment` field, replace the named typed object, restore the assignment list, and re-run complete proposal validation before calculation. Never mutate a source proposal.

- [ ] **Step 3: Add failing independent recalculation tests**

Create retention-downside and usage-upside cases from the same proposal. Assert that the second case retains the source retention rather than the first case's override. Verify numeric deltas for revenue, contribution after fixed costs, active customers, ARPA, and weighted price increase where calculable. Verify added and removed guardrail violations, decision reasons, and status changes.

```python
cases = calculate(payload)["sensitivity_cases"]
self.assertEqual(cases[0]["source_proposal"], "higher-flat-price")
self.assertLess(cases[0]["metrics"]["active_customers"],
                calculate(payload)["proposals"][0]["metrics"]["active_customers"])
self.assertEqual(cases[1]["segments"][0]["retention_rate_after_migration"], Decimal("0.90"))
```

- [ ] **Step 4: Implement sensitivity output and comparisons**

Return the complete recalculated proposal result plus `source_proposal`, numeric `deltas_from_source`, sorted `added_guardrail_violations`, `removed_guardrail_violations`, `added_decision_reasons`, and `removed_decision_reasons`. Use the same current counterfactual and proposal calculator as ordinary proposals.

- [ ] **Step 5: Add CLI tests**

Test valid file input, standard input, malformed JSON, missing files, and validation errors:

```python
def test_cli_reads_standard_input(self):
    stdout = io.StringIO()
    with patch("sys.stdin", io.StringIO(json.dumps(recurring_payload()))), redirect_stdout(stdout):
        status = main(["-"])
    self.assertEqual(status, 0)
    self.assertEqual(json.loads(stdout.getvalue())["mode"], "recurring")
```

Assert success output is compact UTF-8 JSON, integral `Decimal` values serialize as integers, nonintegral decimals serialize as JSON numbers, and every file, JSON, or validation error returns 2 with `error: <message>` on standard error and no numeric result on standard output.

- [ ] **Step 6: Implement the CLI**

Accept one path or `-`, parse floats using `Decimal`, and serialize with:

```python
def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")
```

- [ ] **Step 7: Run all calculator tests and commit**

Run: `python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py`

Expected: validation, formulas, migration, guardrails, sensitivity, and CLI tests all pass.

```bash
git add skills/finance/pricing-decision/scripts
git commit -m "feat: add pricing sensitivity analysis"
```

---

### Task 5: Skill entrypoint and focused references

**Files:**
- Create: `skills/finance/pricing-decision/SKILL.md`
- Create: `skills/finance/pricing-decision/references/intake.md`
- Create: `skills/finance/pricing-decision/references/proposal-design.md`
- Create: `skills/finance/pricing-decision/references/calculation-model.md`
- Create: `skills/finance/pricing-decision/references/migration-policy.md`
- Create: `skills/finance/pricing-decision/references/validation-plan.md`
- Create: `skills/finance/pricing-decision/references/report-format.md`

**Interfaces:**
- Consumes: user materials, aggregate customer evidence, candidate plans, calculator JSON, and calculator output.
- Produces: an evidence-labeled pricing decision, segment migration policy, and validation plan in the user's language.

- [ ] **Step 1: Create the entrypoint**

Use this frontmatter:

```yaml
---
name: pricing-decision
description: Compare price increases, plan and packaging changes, pricing metrics, and discount policies; quantify revenue, contribution, customer migration, and guardrail impact; and design a validation plan for recurring, transactional, or service-project businesses. Use when deciding whether and how to change pricing; do not use for securities pricing, statutory transfer pricing, pricing-page copy alone, or automatic live price changes.
license: MIT
metadata:
  author: ficilcom
---
```

Keep shared workflow and non-negotiable boundaries in `SKILL.md`. Route intake first, proposal design before calculator input, migration policy before proposal calculation, validation planning after output, and report format last.

- [ ] **Step 2: Write `references/intake.md`**

Define source-first intake, evidence states, one-stream boundaries, current-offer reconstruction, usage and billable-base definitions, direct and variable cost scope, current customer and new-customer baselines, retention evidence, contract and renewal constraints, objective selection, guardrails, and minimum useful inputs. Explicitly reject personal or protected-attribute segmentation and unnecessary customer identifiers.

- [ ] **Step 3: Write `references/proposal-design.md`**

Cover the four pricing levers, the four supported formula models, value-metric criteria, package differentiation, discounts and contract periods, next-best alternatives, evidence for willingness to pay, proposal naming, and YAGNI limits. Instruct the agent to create a small set of materially distinct proposals and not infer customer response from competitor prices or cost-plus logic.

- [ ] **Step 4: Write `references/calculation-model.md`**

Document the exact JSON shapes, wrappers, current and proposal formulas, objective and guardrail definitions, charge models, typed states, price bands, sensitivity paths, output keys, and command:

```bash
python3 scripts/calculate_pricing_decision.py <input.json>
```

State that results are decision-horizon run rates, not cumulative cash realization, and that one-time implementation costs are separate.

- [ ] **Step 5: Write `references/migration-policy.md`**

Define criteria and trade-offs for `immediate`, `renewal`, `delayed`, `grandfathered`, `phased`, and `manual_review`. Use segment and contract-cohort rules based on timing, price increase, usage, contribution, service burden, and relationship risk. Strategic account exceptions remain aggregated where possible. Require legal or contract review for notice, renewal, discrimination, regulated pricing, or consumer-protection questions without claiming a conclusion.

- [ ] **Step 6: Write `references/validation-plan.md`**

Route decisive uncertainty to historical analysis, interviews, willingness-to-pay research, nonbinding quotes, new-customer tests, renewal pilots, or phased rollout. Require hypothesis, segment, primary metric, guardrails, duration, sample rationale, stopping conditions, decision rule, dependencies, owner, and authorization checkpoint. Do not fabricate statistical power when baseline variance or sample size is unavailable.

- [ ] **Step 7: Write `references/report-format.md`**

Use the specification's fixed eleven-heading order. Include current definitions, objective, guardrails, proposal metrics and deltas, segment migration, price burden, sensitivity, validation plan, evidence gaps, and authorization boundary. Keep run rate, one-time costs, and cumulative cash distinct; label every material assumption and typed state.

- [ ] **Step 8: Validate the repository and commit the skill**

Run: `python3 scripts/validate_skills.py`

Expected: `Validated 4 skill(s).`

```bash
git add skills/finance/pricing-decision
git commit -m "feat: add pricing decision skill"
```

---

### Task 6: Discovery documentation and behavioral verification

**Files:**
- Modify: `README.md`
- Create outside the repository for execution only: temporary recurring SaaS, transactional commerce, and service-project exercise payloads.

**Interfaces:**
- Consumes: the completed skill and calculator.
- Produces: a discoverable README entry and fresh behavioral evidence across all three business modes.

- [ ] **Step 1: Add the README entry**

Add `pricing-decision` to the available-skills table with a concise description covering pricing proposals, profit impact, segment migration, guardrails, and validation planning.

- [ ] **Step 2: Run the recurring SaaS exercise**

Use a current flat plan, a base-plus-usage proposal, a renewal segment, a grandfathered segment, a transition discount, and a downside sensitivity with unknown or lower retention. Confirm that new and migrated customers use different discount treatment, grandfathered customers remain on the legacy price, CAC or elasticity is not invented, and the uncertain downside becomes `hold_for_evidence` when critical.

- [ ] **Step 3: Run the transactional commerce exercise**

Use a per-transaction current plan represented by base-plus-usage and a percentage proposal with a declared billable base. Confirm percentage charges use the declared base rather than treating it as company revenue, new-customer response is explicit, contribution differs from revenue, and a supplied customer-loss guardrail can reject an otherwise higher-revenue proposal.

- [ ] **Step 4: Run the service-project exercise**

Use flat or quoted project fees, direct delivery cost, phased migration, strategic manual review, and finite project capacity. Confirm manual-review customers remain on legacy economics until resolved, one-time implementation cost is not subtracted from run-rate contribution, and a capacity violation prevents rollout status.

- [ ] **Step 5: Run fresh final verification**

```bash
python3 skills/finance/pricing-decision/scripts/test_calculate_pricing_decision.py
python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py
python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py
python3 tests/test_calculate_score.py
python3 scripts/validate_skills.py
rg -n '\b(TOD[O]|TB[D]|FIXM[E])\b' skills/finance/pricing-decision || true
git diff --check
git status --short
```

Expected: every test process exits 0, four skills validate, placeholder search and `git diff --check` return no output, and the final working tree is clean after commits.

- [ ] **Step 6: Commit discovery documentation**

```bash
git add README.md
git commit -m "docs: list pricing decision skill"
```
