# Repository guidance

This repository contains portable Agent Skills for bootstrapped and capital-efficient startup operators.

## Structure

- Put each public skill at `skills/<category>/<skill-name>/SKILL.md`.
- Use one of the established categories: `finance`, `grants`, `hiring`, `sales`, `marketing`, `operations`, or `management`.
- Add `scripts/`, `references/`, or `assets/` inside a skill only when the workflow needs them.
- Do not commit generated skill scaffolds with `TODO` markers.

## Authoring

- Follow the open Agent Skills specification and the principles in `CONTRIBUTING.md`.
- Keep names lowercase and hyphenated, under 64 characters, and identical to the parent directory.
- Make descriptions say both what the skill does and when it applies.
- Keep the entrypoint concise and route conditional detail to directly linked references.
- Prefer decision criteria and verifiable outcomes to rigid steps when several sound approaches exist.
- Preserve authorization boundaries, especially around applications, transactions, communications, and other external changes.
- For financial, legal, tax, grant, or regulatory facts, verify current authoritative sources when the task depends on them.

## Verification

Run `python3 scripts/validate_skills.py` after changing any skill. Exercise new or substantially revised skills with realistic requests when feasible.
