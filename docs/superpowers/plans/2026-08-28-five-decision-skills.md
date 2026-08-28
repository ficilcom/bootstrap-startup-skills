# Five Decision Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement five portable, deterministic founder decision skills with a shared evidence and analysis-quality contract.

**Architecture:** Each skill is an independent package containing a concise entrypoint, three directly linked references, and one standard-library Python CLI. Tests import each helper directly and exercise its CLI; no Python code is shared between skills.

**Tech Stack:** Markdown, Python 3 standard library, `unittest`, repository validation scripts.

**Spec:** `docs/superpowers/specs/2026-08-28-five-decision-skills-design.md`

## Global Constraints

- Preserve the four evidence states and reject unknown numeric values encoded as zero.
- Default `analysis_mode` to `core`; accept only `core` and `advanced`.
- Return `analysis_quality.mode`, `status`, `evidence_counts`, `decision_changing_unknowns`, and `warnings`.
- Keep economic ordering separate from gates and recommendations.
- Reject duplicate IDs, invalid references, contradictions, boundary violations, and malformed CLI input.
- Keep every skill independently installable and dependency-free.
- Preserve current unrelated and earlier uncommitted changes.

---

### Task 1: Growth experiment review

**Files:**
- Create: `skills/marketing/growth-experiment-review/SKILL.md`
- Create: `skills/marketing/growth-experiment-review/references/intake-and-method.md`
- Create: `skills/marketing/growth-experiment-review/references/calculation-model.md`
- Create: `skills/marketing/growth-experiment-review/references/report-format.md`
- Create: `skills/marketing/growth-experiment-review/scripts/analyze_growth_experiments.py`
- Create: `tests/marketing/growth-experiment-review/test_analyze_growth_experiments.py`

**Interfaces:**
- Consumes evidenced costs, effort, capacity, probability, contribution, sample and thresholds.
- Produces experiment economics, capacity and evidence gates, scenarios, decisions, and `analysis_quality`.

- [ ] Write tests for core calculations, advanced scale/stop/run/hold gates, scenario recalculation, local unknown propagation, threshold contradictions, duplicate IDs, evidence validation, boundaries, and CLI errors.
- [ ] Run the target test and confirm it fails because the module does not exist.
- [ ] Implement the script and documentation with the exact interface described by the spec.
- [ ] Run the target test, repository validator, and full suite; fix only observed failures.
- [ ] Execute one realistic advanced payload and inspect decision, evidence, unknowns, stopping condition, and authorization boundary.

### Task 2: Sales deal qualification

**Files:**
- Create: `skills/sales/sales-deal-qualification/SKILL.md`
- Create: `skills/sales/sales-deal-qualification/references/intake-and-method.md`
- Create: `skills/sales/sales-deal-qualification/references/calculation-model.md`
- Create: `skills/sales/sales-deal-qualification/references/report-format.md`
- Create: `skills/sales/sales-deal-qualification/scripts/qualify_sales_deals.py`
- Create: `tests/sales/sales-deal-qualification/test_qualify_sales_deals.py`

**Interfaces:**
- Consumes dates, evidenced values, must/should criteria, anonymous deals, and advanced deal checks.
- Produces qualification and timing gates, supplied-probability weighted value, recommended action, validation targets, and `analysis_quality`.

- [ ] Write and run failing tests covering eligible, conditional, disqualified and founder-intervention paths plus invalid dates, criteria references, duplicates, evidence, boundaries, and CLI errors.
- [ ] Implement the deterministic helper and concise progressive-disclosure documentation.
- [ ] Run the target test, validator, full suite, and one realistic advanced request before continuing.

### Task 3: Role scorecard and hiring process

**Files:**
- Create: `skills/hiring/role-scorecard-and-hiring-process/SKILL.md`
- Create: `skills/hiring/role-scorecard-and-hiring-process/references/intake-and-method.md`
- Create: `skills/hiring/role-scorecard-and-hiring-process/references/calculation-model.md`
- Create: `skills/hiring/role-scorecard-and-hiring-process/references/report-format.md`
- Create: `skills/hiring/role-scorecard-and-hiring-process/scripts/evaluate_hiring_process.py`
- Create: `tests/hiring/role-scorecard-and-hiring-process/test_evaluate_hiring_process.py`

**Interfaces:**
- Consumes weighted criteria, minimum ratings, evidenced anonymous candidate ratings, and optional required process checks.
- Produces evidence scores, eligibility gates, ranking, process gaps, decisions, stopping conditions, and `analysis_quality`.

- [ ] Write and run failing tests for scoring, hard-gate separation, unknown localization, process gates, duplicate and unknown references, invalid weights/ratings, boundaries, and CLI errors.
- [ ] Implement the script and skill resources without collecting protected traits or authorizing hiring actions.
- [ ] Run the target test, validator, full suite, and one realistic advanced request before continuing.

### Task 4: Capacity and backlog plan

**Files:**
- Create: `skills/operations/capacity-and-backlog-plan/SKILL.md`
- Create: `skills/operations/capacity-and-backlog-plan/references/intake-and-method.md`
- Create: `skills/operations/capacity-and-backlog-plan/references/calculation-model.md`
- Create: `skills/operations/capacity-and-backlog-plan/references/report-format.md`
- Create: `skills/operations/capacity-and-backlog-plan/scripts/analyze_capacity_backlog.py`
- Create: `tests/operations/capacity-and-backlog-plan/test_analyze_capacity_backlog.py`

**Interfaces:**
- Consumes period capacity, classified work demand, contributions, interventions, and scenarios.
- Produces period/cumulative gaps, first breach, at-risk work, acceptance gates, intervention/scenario metrics, and `analysis_quality`.

- [ ] Write and run failing tests for capacity arithmetic, commitment priority, unknown local propagation, interventions, scenarios, invalid periods, references, duplicate IDs, boundaries, and CLI errors.
- [ ] Implement the script and progressive documentation with explicit commitment and authorization boundaries.
- [ ] Run the target test, validator, full suite, and one realistic advanced request before continuing.

### Task 5: Working capital cycle review

**Files:**
- Create: `skills/finance/working-capital-cycle-review/SKILL.md`
- Create: `skills/finance/working-capital-cycle-review/references/intake-and-method.md`
- Create: `skills/finance/working-capital-cycle-review/references/calculation-model.md`
- Create: `skills/finance/working-capital-cycle-review/references/report-format.md`
- Create: `skills/finance/working-capital-cycle-review/scripts/analyze_working_capital.py`
- Create: `tests/finance/working-capital-cycle-review/test_analyze_working_capital.py`

**Interfaces:**
- Consumes evidenced balances and optional evidenced cycle targets and scenarios.
- Produces DSO/DIO/DPO/CCC, net working capital, signed cash release, scenario metrics, validation targets, and `analysis_quality`.

- [ ] Write and run failing tests for ratios, signed cash release, zero denominators, unknown localization, scenarios, contradictory periods, duplicate IDs, evidence and currency validation, boundaries, and CLI errors.
- [ ] Implement the helper and documentation without presenting terms or accounting treatment as professional advice.
- [ ] Run the target test, validator, full suite, and one realistic advanced request.

### Task 6: Catalog and final verification

**Files:**
- Modify: `README.md`

- [ ] Add five catalog rows whose descriptions match the implemented capabilities.
- [ ] Run `python3 scripts/validate_skills.py` and confirm 31 skills validate.
- [ ] Run every target test and `python3 scripts/run_tests.py` with zero failures.
- [ ] Check every local Markdown link, run `git diff --check`, inspect the final diff and status, and report any inability to commit caused by repository permissions.
