# Unit Economics Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable three-mode skill that deterministically calculates gross and contribution economics, CAC, payback, LTV, break-even, diagnostic flags, and sensitivity results.

**Architecture:** A concise `SKILL.md` routes an agent to focused intake, model-selection, calculation, diagnosis, and report references. A standard-library Python module validates anonymous JSON and calculates each scenario and sensitivity case independently; a standard-library `unittest` suite verifies formulas, typed non-calculable states, cross-mode boundaries, and CLI behavior.

**Tech Stack:** Markdown, Python 3 standard library, JSON, `decimal.Decimal`, `unittest`

**Spec:** `docs/superpowers/specs/2026-08-22-unit-economics-diagnostic-design.md`

## Global Constraints

- Create the skill at `skills/finance/unit-economics-diagnostic/` with matching lowercase, hyphenated frontmatter name.
- Use only the Python standard library.
- Analyze one mode, economic unit, currency, revenue basis, and stream per run.
- Support `recurring`, `transactional`, and `service_project`; reject a hybrid mode.
- Keep gross profit, contribution profit, fixed-cost coverage, and acquisition cost scope distinct.
- Represent money with `{amount, evidence}` and scalars with `{value, evidence}`; `unknown` always carries JSON `null`, never numeric zero.
- Treat known zero denominators as typed non-calculable states, not validation failures or infinity.
- Do not hard-code a favorable LTV:CAC or payback benchmark.
- Do not use constant-retention LTV outside recurring mode or return infinite LTV for zero churn.
- Recalculate every scenario and sensitivity case independently.
- Do not authorize price, advertising, budget, staffing, contract, customer-term, communication, or transaction changes.

---

### Task 1: Input schema and validation

**Files:**
- Create: `skills/finance/unit-economics-diagnostic/scripts/calculate_unit_economics.py`
- Create: `skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

**Interfaces:**
- Consumes: JSON-compatible `dict[str, object]` with the scenario shape in the specification.
- Produces: `validate(payload: object) -> dict[str, object]`, `calculate(payload: dict[str, object]) -> dict[str, object]`, and CLI `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing validation tests and a complete recurring fixture**

Create `recurring_payload()` with a base scenario and add focused assertions:

```python
def test_rejects_unknown_money_encoded_as_zero(self):
    payload = recurring_payload()
    payload["scenarios"][0]["drivers"]["price_per_unit"] = money(0, "unknown")
    with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
        calculate(payload)

def test_rejects_constant_retention_for_transactional_mode(self):
    payload = recurring_payload()
    payload["mode"] = "transactional"
    with self.assertRaisesRegex(ValueError, "constant_retention is only valid for recurring"):
        calculate(payload)
```

Also test invalid dates/currencies, mixed optional amount currency, rates above 1, negative values, duplicate scenario names, missing selected CAC basis, non-boolean scope flags, non-integer customer counts, and period-unit mismatch.

- [ ] **Step 2: Run the test file and confirm import failure**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: `ModuleNotFoundError` because the calculator does not exist.

- [ ] **Step 3: Implement typed parsing and schema validation**

Define:

```python
EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"recurring", "transactional", "service_project"}
PERIOD_UNITS = {"week", "month", "quarter", "year"}
CAC_BASES = {"paid", "blended", "fully_loaded", "marginal"}
LTV_METHODS = {"observed_cohort", "fixed_horizon", "constant_retention"}
```

Implement `money_value(entry: object, path: str, currency: str) -> Decimal | None`, `scalar_value(entry: object, path: str, *, rate: bool = False, integer: bool = False) -> Decimal | None`, and `validate(payload: object) -> dict[str, object]`. Validate the top-level fields, required driver keys, acquisition object, selected CAC basis, LTV method-specific keys, optional targets, scenario uniqueness, evidence wrappers, and optional currencies. Allow known zero values but reject non-finite or negative values. Require `analysis_period == ltv_model.period_unit` and constant-retention mode compatibility.

- [ ] **Step 4: Run validation tests**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: validation cases pass; calculation cases are not added yet.

- [ ] **Step 5: Commit validation**

```bash
git add skills/finance/unit-economics-diagnostic/scripts
git commit -m "feat: validate unit economics inputs"
```

---

### Task 2: Unit profit, period totals, and break-even

**Files:**
- Modify: `skills/finance/unit-economics-diagnostic/scripts/calculate_unit_economics.py`
- Modify: `skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

**Interfaces:**
- Consumes: validated driver money/scalar objects and top-level `unit_is_discrete`.
- Produces: `calculate_scenario(scenario: dict[str, object], *, mode: str, analysis_period: str, currency: str, unit_is_discrete: bool) -> dict[str, object]` with `unit_economics`, `period_economics`, `break_even`, `breakpoints`, `missing_inputs`, and `estimate_based`.

- [ ] **Step 1: Add failing formula tests**

Test a recurring fixture with price 12,000, COGS 2,500, other variable cost 1,000, volume 180, and fixed costs 1,200,000:

```python
result = calculate(payload)["scenarios"][0]
self.assertEqual(result["unit_economics"]["gross_profit_per_unit"], 9_500)
self.assertEqual(result["unit_economics"]["contribution_profit_per_unit"], 8_500)
self.assertEqual(result["period_economics"]["revenue"], 2_160_000)
self.assertEqual(result["period_economics"]["contribution_after_fixed_costs"], 330_000)
self.assertEqual(result["break_even"]["units_ceiling"], 142)
```

Add tests for zero price percentage states, negative transactional contribution with `no_finite_break_even`, continuous-unit break-even without ceiling, service-project capacity failure, fixed costs of zero, unknown COGS without zero substitution, and current-volume price breakpoint.

- [ ] **Step 2: Run tests and confirm missing result fields**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: failures identify missing unit and break-even calculations.

- [ ] **Step 3: Implement safe arithmetic and break-even**

Use `Decimal` throughout and return raw numeric values when calculated or stable strings for typed states:

```python
contribution = price - cogs - variable_cost
break_even_units = fixed_costs / contribution
units_ceiling = int(break_even_units.to_integral_value(rounding=ROUND_CEILING))
```

Use `indeterminate` when a required input is unknown, `indeterminate_zero_price` for percentage margins at zero price, `no_finite_break_even` for nonpositive contribution, and `not_applicable_continuous_unit` for a continuous-unit ceiling. Compare the applicable raw or whole-unit requirement with capacity.

- [ ] **Step 4: Implement initial decision breakpoints**

Return minimum price for positive contribution, minimum price for break-even at current volume, and maximum variable cost for positive contribution. Return `indeterminate_zero_volume` when a current-volume breakpoint divides by zero.

- [ ] **Step 5: Run the complete test file**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: validation and unit-profit tests pass.

- [ ] **Step 6: Commit unit economics**

```bash
git add skills/finance/unit-economics-diagnostic/scripts
git commit -m "feat: calculate unit profit and break-even"
```

---

### Task 3: CAC, payback, LTV, and diagnosis

**Files:**
- Modify: `skills/finance/unit-economics-diagnostic/scripts/calculate_unit_economics.py`
- Modify: `skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

**Interfaces:**
- Consumes: calculated contribution, acquisition pools, customer drivers, one LTV model, optional payback target, and capacity result.
- Produces: `cac`, `customer_economics`, additional breakpoints, and `diagnostic_flags`.

- [ ] **Step 1: Add failing CAC and LTV tests**

Cover all supported bases, selected basis, customer contribution, payback, and recurring retention:

```python
scenario = calculate(recurring_payload())["scenarios"][0]
self.assertEqual(scenario["cac"]["by_basis"]["paid"], 8_000)
self.assertEqual(scenario["cac"]["by_basis"]["fully_loaded"], 20_000)
self.assertEqual(scenario["customer_economics"]["payback_periods"], Decimal("2.352941176470588235294117647"))
self.assertEqual(scenario["customer_economics"]["ltv"], 212_500)
self.assertEqual(scenario["customer_economics"]["expected_lifetime_periods"], 25)
```

Add tests for zero churn, fixed-horizon transactional LTV, observed-cohort cumulative payback, zero new customers, zero CAC ratio state, nonpositive customer contribution, paid/blended/fully loaded/marginal separation, incomplete or misaligned CAC scope, and a payback target exceeded while LTV still recovers CAC.

- [ ] **Step 2: Run tests and confirm CAC/LTV failures**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: CAC, customer, and diagnostic fields are missing.

- [ ] **Step 3: Implement CAC and payback**

For every supplied pool, divide by known positive new customers. Return `indeterminate_zero_new_customers` when the known count is zero and `indeterminate` for an unknown count or pool. Compute customer-period contribution from contribution per unit and units per customer per period.

For non-cohort payback, return a number, `not_recoverable`, or `indeterminate`. For observed cohorts, divide each period contribution total by original cohort customers, accumulate, and return the first one-based period reaching selected CAC or `not_observed_within_horizon`.

- [ ] **Step 4: Implement three LTV methods and LTV:CAC**

Implement observed cumulative contribution, fixed-horizon expected units, and constant-retention contribution/churn. Return `zero_churn_requires_fixed_horizon_or_cohort` at zero churn. Return `not_meaningful_zero_cac` for the ratio at selected CAC zero.

- [ ] **Step 5: Implement diagnostic flags**

Return nonexclusive flags from explicit conditions. `profitable_to_scale` requires positive contribution, break-even within supplied capacity, complete and aligned CAC scope, CAC recovery within the credible method horizon, and compliance with a supplied max-payback target. Use `positive_unit_economics_unassessed_acquisition` when missing acquisition or capacity evidence prevents that claim.

- [ ] **Step 6: Implement acquisition breakpoints**

Return maximum CAC for a supplied payback target and maximum constant churn for LTV to equal selected CAC. Clamp the churn breakpoint to 1 and return a companion constraint status when the raw breakpoint exceeds 1.

- [ ] **Step 7: Run all tests and commit**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: all validation, unit, CAC, LTV, and diagnosis tests pass.

```bash
git add skills/finance/unit-economics-diagnostic/scripts
git commit -m "feat: diagnose acquisition and lifetime economics"
```

---

### Task 4: Scenario comparison, sensitivity, and CLI

**Files:**
- Modify: `skills/finance/unit-economics-diagnostic/scripts/calculate_unit_economics.py`
- Modify: `skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

**Interfaces:**
- Consumes: validated scenarios and sensitivity cases with supported typed override paths.
- Produces: `comparison_to_base`, top-level `sensitivity_cases`, and compact JSON CLI behavior.

- [ ] **Step 1: Add failing scenario and sensitivity tests**

Create a downside scenario where price falls and CAC rises, then assert contribution, payback, and flag differences. Add one-variable and multi-variable cases:

```python
payload["sensitivity_cases"] = [{
    "name": "price-down-and-cogs-up",
    "source_scenario": "base",
    "overrides": {
        "drivers.price_per_unit": money(10_800, "estimated"),
        "drivers.cogs_per_unit": money(3_000, "estimated"),
    },
}]
case = calculate(payload)["sensitivity_cases"][0]
self.assertEqual(case["source_scenario"], "base")
self.assertIn("contribution_profit_per_unit", case["deltas"])
```

Test that cases do not stack, added and removed flags are reported, unsupported structural paths fail validation, observed cohort contribution-list overrides work, and duplicate sensitivity names fail.

- [ ] **Step 2: Run tests and confirm sensitivity failures**

Run: `python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: comparison and sensitivity outputs are missing.

- [ ] **Step 3: Implement comparisons and independent overrides**

Deep-copy the named source scenario per case, apply only its overrides, revalidate the modified scenario, and call the same scenario calculator. Return numeric deltas where both source and result are numeric, plus sorted `added_flags` and `removed_flags`. Never mutate or stack source scenarios.

- [ ] **Step 4: Implement CLI and JSON serialization**

Accept a path or `-`, parse floats as `Decimal`, serialize integral decimals as integers and other decimals as floats, print UTF-8 compact JSON to stdout, and return 2 with `error: <message>` on stderr for file, JSON, or validation failures.

- [ ] **Step 5: Add CLI tests and run the suite**

Test valid file input, stdin, malformed JSON, and validation errors. Run:

`python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py`

Expected: all tests pass.

- [ ] **Step 6: Commit scenarios, sensitivity, and CLI**

```bash
git add skills/finance/unit-economics-diagnostic/scripts
git commit -m "feat: add unit economics sensitivity analysis"
```

---

### Task 5: Skill entrypoint and focused references

**Files:**
- Create: `skills/finance/unit-economics-diagnostic/SKILL.md`
- Create: `skills/finance/unit-economics-diagnostic/references/intake.md`
- Create: `skills/finance/unit-economics-diagnostic/references/model-selection.md`
- Create: `skills/finance/unit-economics-diagnostic/references/calculation-model.md`
- Create: `skills/finance/unit-economics-diagnostic/references/diagnosis-rules.md`
- Create: `skills/finance/unit-economics-diagnostic/references/report-format.md`

**Interfaces:**
- Consumes: user materials, focused follow-up answers, and calculator JSON.
- Produces: an evidence-labeled unit-economics diagnosis in the user’s language.

- [ ] **Step 1: Create the entrypoint**

Use this frontmatter and keep mode-specific formulas in references:

```yaml
---
name: unit-economics-diagnostic
description: Diagnose whether each sale or customer creates contribution profit, calculate gross margin, CAC payback, defensible LTV, break-even volume, and sensitivity for recurring, transactional, or service-project businesses. Use when evaluating unit profitability or whether growth economics support scaling; do not use for statutory accounting, valuation, market sizing, or cash-runway forecasting.
license: MIT
metadata:
  author: ficilcom
---
```

Route intake and model selection first, calculation before JSON preparation, diagnosis after calculator output, and report format last.

- [ ] **Step 2: Write intake and model-selection references**

Define source-first intake, evidence states, economic-unit selection, revenue basis, cost allocation, mode choice, stream separation, marketplace GMV boundary, service delivery labor, CAC scope, and minimum useful inputs.

- [ ] **Step 3: Write calculation-model reference**

Document the exact JSON schema, money/scalar wrappers, three LTV methods, formulas, typed states, supported sensitivity paths, output keys, and command:

```bash
python3 scripts/calculate_unit_economics.py <input.json>
```

- [ ] **Step 4: Write diagnosis and report references**

Define every flag, the no-universal-benchmark rule, CAC completeness/alignment conditions, capacity logic, sensitivity priority, and the fixed report heading order. Preserve authorization boundaries for price, campaign, budget, staffing, contract, and communication changes.

- [ ] **Step 5: Validate the repository**

Run: `python3 scripts/validate_skills.py`

Expected: `Validated 3 skill(s).`

- [ ] **Step 6: Commit the skill**

```bash
git add skills/finance/unit-economics-diagnostic
git commit -m "feat: add unit economics diagnostic skill"
```

---

### Task 6: README and behavioral verification

**Files:**
- Modify: `README.md`
- Create outside the repository for execution only: temporary SaaS, e-commerce, and service-project exercise payloads.

**Interfaces:**
- Consumes: completed skill and calculator.
- Produces: a discoverable skill entry and evidence from three realistic business models.

- [ ] **Step 1: Add the README entry**

Add `unit-economics-diagnostic` to the available-skills table with a concise description covering contribution economics, acquisition recovery, break-even, and sensitivity.

- [ ] **Step 2: Run the SaaS exercise**

Use monthly customer economics with paid and fully loaded CAC, churn, infrastructure cost, and a downside retention scenario. Confirm no infinite zero-churn result, CAC bases stay separate, and the downside changes payback or flags.

- [ ] **Step 3: Run the e-commerce exercise**

Use net order revenue, product cost, refunds, payment fees, shipping, paid acquisition, and fixed-horizon repeat orders. Confirm gross and contribution margin differ and the 12-month LTV horizon remains visible.

- [ ] **Step 4: Run the service-project exercise**

Use project price, direct delivery labor, other variable delivery cost, fixed overhead, project capacity, repeat engagements, and an unknown owner-time allocation case. Confirm capacity can make break-even infeasible and unknown allocation does not become zero.

- [ ] **Step 5: Run fresh final verification**

```bash
python3 skills/finance/unit-economics-diagnostic/scripts/test_calculate_unit_economics.py
python3 scripts/validate_skills.py
rg -n '\b(TOD[O]|TB[D]|FIXM[E])\b' skills/finance/unit-economics-diagnostic || true
git diff --check
git status --short
```

Expected: all calculator tests pass, three skills validate, placeholder search and `git diff --check` return no output, and the final working tree is clean after commits.

- [ ] **Step 6: Commit discovery documentation**

```bash
git add README.md
git commit -m "docs: list unit economics diagnostic skill"
```
