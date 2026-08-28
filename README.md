# Bootstrap Startup Skills

Practical AI skills for founders building capital-efficient companies with revenue, debt, grants, automation, and disciplined hiring.

This repository is a collection of portable [Agent Skills](https://agentskills.io/) for bootstrapped and capital-efficient startups. Each skill is independently installable and follows the open Agent Skills specification.

## What belongs here

Skills in this repository should help founders make concrete operating decisions across areas such as:

- non-dilutive financing, bank debt, and grants;
- cash flow, runway, pricing, and capital allocation;
- hiring, outsourcing, and automation;
- sales, marketing, operations, and management cadence.

The collection favors practical decisions, explicit assumptions, and useful artifacts over generic business advice.

## Repository structure

```text
bootstrap-startup-skills/
├── skills/
│   ├── finance/
│   │   └── <skill-name>/
│   │       ├── SKILL.md      # required
│   │       ├── scripts/      # optional deterministic helpers
│   │       ├── references/   # optional on-demand guidance
│   │       └── assets/       # optional output templates
│   ├── grants/
│   ├── hiring/
│   ├── sales/
│   ├── marketing/
│   ├── operations/
│   └── management/
├── scripts/
│   ├── new_skill.py
│   ├── run_tests.py
│   └── validate_skills.py
├── tests/
│   └── <category>/
│       └── <skill-name>/
│           └── test_*.py
└── CONTRIBUTING.md
```

Skill directories live one level below a category. The skill directory name and the `name` in `SKILL.md` must match.

| Category | Scope |
| --- | --- |
| `finance` | Bank debt, lender readiness, refinancing, cash flow, runway, budgeting, unit economics, and capital allocation |
| `grants` | Grant and subsidy discovery, eligibility, and application planning |
| `hiring` | Hiring plans, role design, compensation, and hire-versus-outsource decisions |
| `sales` | Pipeline, sales process, forecasting, and commercial execution |
| `marketing` | Positioning, acquisition, campaigns, and budget allocation |
| `operations` | Processes, automation, vendors, and operating efficiency |
| `management` | Founder reviews, decision systems, planning, and organizational cadence |

## Available skills

| Category | Skill | Description |
| --- | --- | --- |
| Finance | [`accounts-receivable-control`](skills/finance/accounts-receivable-control/) | Age receivables, identify customer exposure and collection blockers, separate payment commitments by evidence, and prioritize cash-protecting collection actions. |
| Finance | [`bank-loan-readiness`](skills/finance/bank-loan-readiness/) | Assess application readiness for Japanese startup and operating-company loans, identify weaknesses, and prioritize improvements. |
| Finance | [`cash-runway-planner`](skills/finance/cash-runway-planner/) | Build a cash-basis 13-week forecast and 12-month runway, compare downside scenarios, and prioritize dated actions before cash or an operating buffer runs short. |
| Finance | [`customer-concentration-risk`](skills/finance/customer-concentration-risk/) | Diagnose revenue, gross-profit, and cash-collection concentration; quantify major-customer loss scenarios; and build a diversification plan. |
| Finance | [`debt-service-capacity`](skills/finance/debt-service-capacity/) | Rebuild the repayment schedule to measure debt service coverage, repayment years, and additional borrowing headroom, and surface the conditions that make a restructuring discussion with the lender worth starting. |
| Finance | [`expense-and-saas-audit`](skills/finance/expense-and-saas-audit/) | Identify defensible expense and SaaS reductions, quantify net savings and timing, and separate safe preparation from changes requiring validation. |
| Finance | [`pricing-decision`](skills/finance/pricing-decision/) | Compare pricing and packaging proposals, quantify revenue and contribution impact, plan segment-level customer migration, apply explicit guardrails, and design validation before rollout. |
| Finance | [`tax-and-social-insurance-calendar`](skills/finance/tax-and-social-insurance-calendar/) | Place Japanese tax, withholding, resident-tax, social-insurance, and labour-insurance payments on a monthly cash schedule, find the first cash-buffer breach, and export the obligations into a runway forecast. |
| Finance | [`unit-economics-diagnostic`](skills/finance/unit-economics-diagnostic/) | Diagnose contribution economics, CAC recovery, defensible LTV, feasible break-even volume, and decision-changing sensitivities across recurring, transactional, and service-project businesses. |
| Finance | [`working-capital-cycle-review`](skills/finance/working-capital-cycle-review/) | Analyze DSO, DIO, DPO, cash conversion cycle, net working capital, user-defined cash-release targets, and balance scenarios without automatically changing commercial or accounting records. |
| Grants | [`grant-application-readiness`](skills/grants/grant-application-readiness/) | Score a grant application package across narrative sections, official scoring criteria, and required documents, then back-schedule the remaining gaps against the submission deadline and available hours. |
| Grants | [`grant-execution-and-reporting`](skills/grants/grant-execution-and-reporting/) | Plan post-award execution by reconciling committed spend against the approved cost breakdown, checking procurement and evidence gaps that create clawback exposure, and sizing the bridge financing needed while the subsidy is paid in arrears. |
| Grants | [`grant-subsidy-fit`](skills/grants/grant-subsidy-fit/) | Decide whether grant or subsidy research is worthwhile and assess a specific program using current official requirements, deadlines, funding mechanics, and application effort. |
| Hiring | [`first-hire-affordability`](skills/hiring/first-hire-affordability/) | Determine whether a first employee is affordable using fully loaded employment cost, cash buffers, downside scenarios, and the earliest defensible start date. |
| Hiring | [`hire-outsource-automate`](skills/hiring/hire-outsource-automate/) | Compare hiring, outsourcing, automation, and deferral using total cost, payback, execution conditions, and operational risks. |
| Hiring | [`role-scorecard-and-hiring-process`](skills/hiring/role-scorecard-and-hiring-process/) | Compare anonymized candidates using role outcomes, competencies, must-have evidence, process gates, and weight sensitivity while keeping scores separate from hiring eligibility. |
| Marketing | [`channel-economics-review`](skills/marketing/channel-economics-review/) | Compare acquisition channels using aligned blended and marginal CAC, contribution payback, retention assumptions, and capacity constraints. |
| Marketing | [`customer-retention-review`](skills/marketing/customer-retention-review/) | Diagnose logo and recurring-revenue retention, expansion, contraction, churn reasons, and upcoming renewal exposure using aligned cohorts. |
| Marketing | [`growth-experiment-review`](skills/marketing/growth-experiment-review/) | Compare growth experiments using expected economics, execution capacity, sample sufficiency, explicit success and stop gates, and user-defined downside scenarios. |
| Marketing | [`offer-portfolio-review`](skills/marketing/offer-portfolio-review/) | Compare products and services using contribution, capacity, demand evidence, downside scenarios, offer relationships, strategic fit, and exit gates. |
| Sales | [`founder-led-sales-review`](skills/sales/founder-led-sales-review/) | Diagnose founder-led sales bottlenecks using aligned pipeline conversion, velocity, ageing, loss reasons, and next actions. |
| Sales | [`sales-deal-qualification`](skills/sales/sales-deal-qualification/) | Qualify individual deals using must/should evidence, supplied probabilities, timing, advanced process gates, and explicit continue, hold, exit, or founder-intervention signals. |
| Sales | [`sales-forecast-confidence`](skills/sales/sales-forecast-confidence/) | Calibrate sales forecasts using historical error, stage ranges, pipeline coverage, opportunity timing, ageing, and customer concentration. |
| Operations | [`business-continuity-check`](skills/operations/business-continuity-check/) | Compare dependency recovery and data-loss capability with tolerated limits, test compound failures and alternatives, and prioritize continuity work. |
| Operations | [`capacity-and-backlog-plan`](skills/operations/capacity-and-backlog-plan/) | Reconcile committed work, backlog, qualified demand, due periods, and capacity; identify the first breach; and compare intervention and downside scenarios. |
| Operations | [`process-bottleneck-audit`](skills/operations/process-bottleneck-audit/) | Identify operating constraints through capacity, work-in-progress, waiting, blocking, rework, and end-to-end throughput. |
| Operations | [`vendor-selection-review`](skills/operations/vendor-selection-review/) | Compare vendors using lifecycle cost, requirement evidence, usage scenarios, contract and exit gates, fit, and reliability. |
| Management | [`founder-time-allocation`](skills/management/founder-time-allocation/) | Review founder time using observed hours, focus fragmentation, founder necessity, value, leverage, and transition economics. |
| Management | [`monthly-budget-variance-review`](skills/management/monthly-budget-variance-review/) | Separate monthly budget variances through data quality, definition changes, timing, mix, and real business change, decompose price, volume, and mix effects, and set corrective actions. |
| Management | [`quarterly-capital-allocation`](skills/management/quarterly-capital-allocation/) | Compare quarterly investment portfolios through base and downside cash paths, buffer resilience, payback, strategic fit, and reversibility. |
| Management | [`weekly-founder-review`](skills/management/weekly-founder-review/) | Turn prior commitments, a small KPI set, anomalies, and open decisions into accountable priorities for the next week. |

## Install

List the available skills:

```bash
npx skills add ficilcom/bootstrap-startup-skills --list
```

Install one skill globally for Codex:

```bash
npx skills add ficilcom/bootstrap-startup-skills \
  --skill <skill-name> \
  --agent codex \
  --global
```

Install `bank-loan-readiness` globally for Codex:

```bash
npx skills add ficilcom/bootstrap-startup-skills \
  --skill bank-loan-readiness \
  --agent codex \
  --global
```

Install all skills interactively:

```bash
npx skills add ficilcom/bootstrap-startup-skills
```

The [`skills` CLI](https://github.com/vercel-labs/skills) also supports Claude Code, Cursor, OpenCode, and many other agents.

## Develop

Create a new skill scaffold:

```bash
python3 scripts/new_skill.py <category> <skill-name>
```

Then replace every `TODO` in the generated `SKILL.md` and add only the supporting resources the workflow actually needs.

Validate every skill:

```bash
python3 scripts/validate_skills.py
```

Run every repository test:

```bash
python3 scripts/run_tests.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the authoring principles and review checklist.

## License

[MIT](LICENSE) © 2026 フィシルコム株式会社
