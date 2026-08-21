#!/usr/bin/env python3
"""Create a minimal Agent Skill scaffold under skills/."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORIES = (
    "finance",
    "grants",
    "hiring",
    "sales",
    "marketing",
    "operations",
    "management",
)
ROOT = Path(__file__).resolve().parents[1]


def title_from_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", choices=CATEGORIES, help="skill category")
    parser.add_argument("name", help="lowercase, hyphenated skill name")
    args = parser.parse_args()
    name = args.name

    if len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        parser.error(
            "name must be at most 64 characters and contain only lowercase "
            "letters, digits, and single hyphens"
        )

    skill_dir = ROOT / "skills" / args.category / name
    skill_file = skill_dir / "SKILL.md"
    if skill_dir.exists():
        parser.error(f"skill already exists: {skill_dir.relative_to(ROOT)}")

    skill_dir.mkdir(parents=True)
    skill_file.write_text(
        f"""---
name: {name}
description: "TODO: Explain what this skill does and when to use it."
license: MIT
metadata:
  author: ficilcom
---

# {title_from_name(name)}

TODO: Define the outcome, essential workflow, and non-obvious constraints.
""",
        encoding="utf-8",
    )
    print(f"Created {skill_file.relative_to(ROOT)}")
    print("Replace every TODO before committing the skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
