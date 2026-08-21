# Cash Runway Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable skill that deterministically calculates 13-week cash forecasts, 12-month runway, warning thresholds, scenario differences, and modeled action effects.

**Architecture:** A concise `SKILL.md` routes the agent to focused intake, calculation, action, and report references. A standard-library Python module validates anonymous JSON, calculates each scenario, and recalculates explicitly expanded action adjustments; a standard-library `unittest` suite verifies arithmetic and rejection behavior.

**Tech Stack:** Markdown, Python 3 standard library, JSON, `unittest`

**Spec:** `docs/superpowers/specs/2026-08-22-cash-runway-planner-design.md`

## Global Constraints

- Create the skill at `skills/finance/cash-runway-planner/` with matching lowercase, hyphenated frontmatter name.
- Use only the Python standard library.
- Model cash receipts and payments, not accounting revenue or profit.
- Keep `gross_cash`, `restricted_cash`, and `minimum_cash_buffer` separate.
- Represent every material amount as `confirmed`, `reported`, `estimated`, or `unknown`; an unknown amount is JSON `null`, never numeric zero.
- Produce quick-mode results as provisional.
- In detailed mode, require 13 consecutive weekly periods followed by consecutive monthly periods through the 12-month horizon.
- Do not extrapolate beyond the modeled horizon; return `more_than_12_months` when no threshold is crossed.
- Do not authorize or perform external communications, cancellations, payment changes, applications, or transactions.
- Verify current authoritative sources only when a user’s decision depends on current legal, tax, grant, financing, or regulatory facts.

---

### Task 1: Calculator schema and validation

**Files:**
- Create: `skills/finance/cash-runway-planner/scripts/calculate_runway.py`
- Create: `skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

**Interfaces:**
- Consumes: JSON-compatible `dict[str, object]` using the schema in `references/calculation-model.md`.
- Produces: `calculate(payload: dict[str, object]) -> dict[str, object]`, `validate(payload: object) -> dict[str, object]`, and CLI `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Create failing validation tests**

Add a test helper that produces a complete base payload and tests unknown handling, duplicate IDs, currencies, restricted cash, period continuity, and detailed-mode weekly coverage. The core rejection assertions are:

```python
def test_rejects_unknown_encoded_as_zero(self):
    payload = detailed_payload()
    payload["gross_cash"] = {"amount": 0, "evidence": "unknown"}
    with self.assertRaisesRegex(ValueError, "unknown amount must be null"):
        calculate(payload)

def test_rejects_restricted_cash_above_gross_cash(self):
    payload = detailed_payload()
    payload["restricted_cash"]["amount"] = 2_000_001
    with self.assertRaisesRegex(ValueError, "restricted_cash cannot exceed gross_cash"):
        calculate(payload)
```

- [ ] **Step 2: Run the focused suite and confirm it fails**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: import or missing-function failure because `calculate_runway.py` is not implemented.

- [ ] **Step 3: Implement schema validation**

Define the stable constants and public function:

```python
EVIDENCE_STATES = {"confirmed", "reported", "estimated", "unknown"}
MODES = {"quick", "detailed"}
GRANULARITIES = {"week", "month"}
DIRECTIONS = {"inflow", "outflow"}

def validate(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    # Validate the top-level currency and money objects, scenario names,
    # unique IDs, periods, movements, optional policy, and actions.
    return payload
```

Use `Decimal(str(value))` for money and reject booleans, non-finite values, and negative amounts. Require `amount is None` exactly when evidence is `unknown`. Require a base scenario, a top-level ISO 4217-style three-letter currency code, and any movement-level currency to match it.

For periods, parse ISO dates, require `start_date <= end_date`, require the first period to start on `as_of_date`, and require every later period to start one day after the prior end. Detailed mode requires the first 13 periods to be weekly, later periods to be monthly, and the final period to end on `add_months(as_of_date, 12) - 1 day`.

- [ ] **Step 4: Run validation tests**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: validation cases pass; calculation cases remain failing until Task 2.

- [ ] **Step 5: Commit the validation layer**

```bash
git add skills/finance/cash-runway-planner/scripts
git commit -m "feat: validate cash runway inputs"
```

---

### Task 2: Scenario balances, runway, and warnings

**Files:**
- Modify: `skills/finance/cash-runway-planner/scripts/calculate_runway.py`
- Modify: `skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

**Interfaces:**
- Consumes: validated scenarios containing ordered period objects and movement money objects.
- Produces: `calculate_scenario(...) -> dict[str, object]`, scenario comparisons, and top-level `warning_status`, `provisional`, and `missing_core_inputs`.

- [ ] **Step 1: Add failing arithmetic tests**

Cover stable runway, a buffer crossing without zero crossing, a zero crossing with funding gap, delayed collections, boundary payments, quick-mode provisional output, and restricted cash separation. Assert exact values such as:

```python
result = calculate(payload)
base = result["scenarios"][0]
self.assertEqual(result["opening_available_cash"], 1_500_000)
self.assertEqual(base["periods"][0]["closing_available_cash"], 1_400_000)
self.assertEqual(base["maximum_funding_gap"], 0)
self.assertEqual(base["buffer_runway"], "more_than_12_months")
self.assertEqual(base["warning_status"], "stable")
```

- [ ] **Step 2: Run the arithmetic tests and confirm failure**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: failures show missing scenario result fields.

- [ ] **Step 3: Implement period and threshold calculation**

Use these formulas and stable output keys:

```python
closing = opening + inflows - outflows
funding_gap = max(Decimal("0"), minimum_buffer - lowest_closing)
runway_months = Decimal(elapsed_days) / Decimal("30.4375")
```

For each period output `opening_available_cash`, `cash_inflows`, `cash_outflows`, `net_cash_flow`, and `closing_available_cash`. Capture the first period ending strictly below the buffer and strictly below zero. Use the period end date as the authoritative crossing date. Return `more_than_12_months` when a threshold is never crossed.

Default warning thresholds are 13 weeks, 6 months, and the 12-month horizon. Allow an optional validated `warning_policy` with ascending `critical_days`, `warning_days`, and `watch_days` values. Set `indeterminate` when a core amount or scenario movement is unknown.

- [ ] **Step 4: Add base-scenario differences**

For every non-base scenario return:

```python
comparison_to_base = {
    "lowest_cash_delta": scenario_lowest - base_lowest,
    "maximum_funding_gap_delta": scenario_gap - base_gap,
    "buffer_crossing_days_delta": nullable_day_difference,
    "zero_crossing_days_delta": nullable_day_difference,
}
```

- [ ] **Step 5: Run all calculator tests**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: all scenario and validation tests defined so far pass.

- [ ] **Step 6: Commit scenario calculation**

```bash
git add skills/finance/cash-runway-planner/scripts
git commit -m "feat: calculate cash runway scenarios"
```

---

### Task 3: Modeled actions and CLI contract

**Files:**
- Modify: `skills/finance/cash-runway-planner/scripts/calculate_runway.py`
- Modify: `skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

**Interfaces:**
- Consumes: actions with `id`, `label`, `scenarios`, `start_period`, `end_period`, `recurrence`, expanded `cash_effects`, and expanded `implementation_costs`.
- Produces: `modeled_actions` entries containing baseline metrics, adjusted metrics, and deltas; CLI JSON on stdout and `error: ...` on stderr with exit status 2.

- [ ] **Step 1: Add failing action and CLI tests**

Model recurring savings with a one-time implementation cost by expanding both into period adjustments:

```python
payload["modeled_actions"] = [{
    "id": "reduce_tools",
    "label": "Reduce unused software",
    "scenarios": ["base"],
    "start_period": "w03",
    "end_period": "m12",
    "recurrence": "expanded",
    "cash_effects": [
        {"period_id": "w03", "amount": {"amount": 25_000, "evidence": "estimated"}},
        {"period_id": "w04", "amount": {"amount": 25_000, "evidence": "estimated"}},
    ],
    "implementation_costs": [
        {"period_id": "w03", "amount": {"amount": 10_000, "evidence": "reported"}},
    ],
}]
```

Assert that the adjusted w03 balance rises by 15,000, later cash effects rise by their full amount, and action deltas match recalculated scenario metrics. Invoke `main([path])` for a valid file and malformed JSON.

- [ ] **Step 2: Run tests and confirm action failures**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: action result is missing or unchanged.

- [ ] **Step 3: Implement independent action recalculation**

Copy only the target scenario’s validated period data, apply each expanded positive cash effect and implementation cost to its matching period, and call the same scenario calculator. Do not stack unrelated actions; each action compares independently with the original target scenario.

Return one result per action and target scenario with:

```python
{
    "action_id": action["id"],
    "scenario": scenario_name,
    "gross_cash_effect": sum_cash_effects,
    "implementation_cost": sum_costs,
    "net_cash_effect": sum_cash_effects - sum_costs,
    "adjusted": adjusted_summary,
    "delta": metric_differences,
}
```

- [ ] **Step 4: Implement the CLI**

Accept a JSON path or `-` for stdin, parse floats as `Decimal`, serialize `Decimal` as an integer when integral and otherwise as a float, and print compact UTF-8 JSON. Catch `OSError`, `json.JSONDecodeError`, and `ValueError`, write `error: <message>` to stderr, and return 2.

- [ ] **Step 5: Run the complete test file**

Run: `python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py`

Expected: all tests pass.

- [ ] **Step 6: Commit modeled actions and CLI**

```bash
git add skills/finance/cash-runway-planner/scripts
git commit -m "feat: model runway improvement actions"
```

---

### Task 4: Skill instructions and focused references

**Files:**
- Create: `skills/finance/cash-runway-planner/SKILL.md`
- Create: `skills/finance/cash-runway-planner/references/intake.md`
- Create: `skills/finance/cash-runway-planner/references/calculation-model.md`
- Create: `skills/finance/cash-runway-planner/references/action-ladder.md`
- Create: `skills/finance/cash-runway-planner/references/report-format.md`

**Interfaces:**
- Consumes: user materials, focused follow-up answers, and the calculator JSON contract.
- Produces: an evidence-labeled cash runway report in the user’s language.

- [ ] **Step 1: Create the concise entrypoint**

Use this frontmatter and keep detailed formulas out of the entrypoint:

```yaml
---
name: cash-runway-planner
description: Build a cash-basis 13-week forecast and 12-month runway estimate, identify buffer or cash shortfalls, compare scenarios, and prioritize dated runway actions for bootstrapped or capital-efficient businesses. Use for cash runway, liquidity planning, downside forecasting, or deciding when and what spending to reduce; do not use for statutory cash-flow statements or personal budgeting.
license: MIT
metadata:
  author: ficilcom
---
```

Route intake first, calculation details before preparing JSON, action guidance only when actions are requested or a warning is present, and report format last.

- [ ] **Step 2: Write intake and evidence guidance**

Define quick and detailed mode selection, the minimum inputs, materiality-based follow-up questions, safe document handling, scenario choice, and the four evidence states. Require the agent to inspect provided records before asking the user to repeat facts.

- [ ] **Step 3: Write the calculator contract**

Document the exact JSON fields used by Tasks 1–3, period-boundary rules, money-object semantics, action expansion, formulas, output keys, and command:

```bash
python3 scripts/calculate_runway.py <input.json>
```

- [ ] **Step 4: Write action and report contracts**

Define the six-level action order from the spec, the decision criteria for each action, protected/high-consequence payment categories, and a fixed report heading order. Require dates, modeled net effects, confidence, missing evidence, and explicit authorization boundaries.

- [ ] **Step 5: Run repository validation**

Run: `python3 scripts/validate_skills.py`

Expected: `Validated 2 skill(s).`

- [ ] **Step 6: Commit the skill instructions**

```bash
git add skills/finance/cash-runway-planner
git commit -m "feat: add cash runway planner skill"
```

---

### Task 5: Discovery documentation and forward exercises

**Files:**
- Modify: `README.md`
- Create outside the repository for execution only: temporary SaaS and services JSON fixtures and generated reports.

**Interfaces:**
- Consumes: completed skill and calculator.
- Produces: discoverable README entry and evidence that the skill behaves realistically.

- [ ] **Step 1: Add the README entry**

Add `cash-runway-planner` to the available-skills table with a concise description matching its discovery scope.

- [ ] **Step 2: Run the SaaS exercise**

Create a temporary detailed payload with delayed receivables, an annual software renewal, and a planned hire. Run the calculator, then inspect that the forecast uses receipt dates, the downside scenario changes the threshold date, and deferring the hire is presented as a decision rather than an automatic action.

- [ ] **Step 3: Run the services exercise**

Create a temporary payload with uneven project collections, contractor payments, and an unknown tax-related amount. Confirm that the result becomes provisional or indeterminate where appropriate, does not encode the unknown as zero, and calls for authoritative or professional confirmation rather than advising non-payment.

- [ ] **Step 4: Run all verification commands**

Run:

```bash
python3 skills/finance/cash-runway-planner/scripts/test_calculate_runway.py
python3 scripts/validate_skills.py
rg -n '\b(TOD[O]|TB[D]|FIXM[E])\b' skills/finance/cash-runway-planner README.md
git diff --check
```

Expected: calculator tests pass, two skills validate, placeholder search returns no matches, and `git diff --check` returns no output.

- [ ] **Step 5: Commit discovery documentation**

```bash
git add README.md
git commit -m "docs: list cash runway planner skill"
```

- [ ] **Step 6: Review the final diff and status**

Run: `git status --short && git log -6 --oneline`

Expected: the working tree is clean and the plan, calculator, skill resources, and README commits are present.
