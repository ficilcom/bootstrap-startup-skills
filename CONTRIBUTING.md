# Contributing

Contributions should turn a recurring founder task into a focused, reusable workflow. A skill should improve an agent's decisions or outputs with domain knowledge, a reliable process, or useful resources.

## Create a skill

Start with the repository helper:

```bash
python3 scripts/new_skill.py <category> <skill-name>
```

Choose one of the repository's established categories, then use a short, action-oriented skill name made of lowercase letters, digits, and hyphens. Keep the frontmatter `name` identical to the skill directory name.

Every `SKILL.md` needs at least:

```yaml
---
name: example-skill
description: Explain what the skill does and the situations in which an agent should use it.
license: MIT
---
```

The description is discovery metadata. Make it specific enough to activate for relevant requests without attracting unrelated work.

## Authoring principles

- Assume the agent is capable. Include guidance that changes decisions, prevents a realistic failure, or provides non-obvious domain context.
- Preserve the user's objective, constraints, and authority. A skill must not silently expand the requested work or authorize external actions.
- Prefer explicit inputs, assumptions, decision criteria, and a useful deliverable over generic advice.
- Keep `SKILL.md` focused. Move conditional detail into `references/`, repeated deterministic work into `scripts/`, and reusable output materials into `assets/`.
- Link supporting files from `SKILL.md` with paths relative to the skill directory. Do not add resource directories unless they serve a concrete purpose.
- Do not duplicate material across `SKILL.md` and references.

## Business and financial quality

Many skills in this repository touch consequential business decisions. They should:

- distinguish user-provided facts, sourced facts, estimates, and assumptions;
- show calculations and important sensitivities when producing financial conclusions;
- use current, authoritative sources for laws, grants, taxes, rates, or jurisdiction-specific requirements;
- state material uncertainty and avoid presenting legal, tax, or accounting guidance as a professional determination;
- request authorization immediately before any external submission, transaction, message, or other consequential mutation;
- avoid collecting or exposing sensitive company or personal data that the task does not require.

## Validate

Run the repository checks before submitting a change:

```bash
python3 scripts/validate_skills.py
```

For a new or substantially changed skill, also test at least one realistic request and inspect the actual output rather than checking only headings or wording.

## Review checklist

- The skill solves a specific, recurring founder task.
- Its name and description make discovery predictable.
- The instructions preserve user intent and decision authority.
- The workflow produces a concrete and useful result.
- Sources, calculations, and uncertainty are handled appropriately.
- Supporting resources are linked and used, with no placeholders or dead files.
- The repository validator passes.
