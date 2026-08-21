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
│   └── validate_skills.py
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

| Skill | Description |
| --- | --- |
| [`bank-loan-readiness`](skills/finance/bank-loan-readiness/) | Assess application readiness for Japanese startup and operating-company loans, identify weaknesses, and prioritize improvements. |
| [`cash-runway-planner`](skills/finance/cash-runway-planner/) | Build a cash-basis 13-week forecast and 12-month runway, compare downside scenarios, and prioritize dated actions before cash or an operating buffer runs short. |

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the authoring principles and review checklist.

## License

[MIT](LICENSE) © 2026 フィシルコム株式会社
