#!/usr/bin/env python3
"""Validate repository-level invariants for Agent Skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORIES = {
    "finance",
    "grants",
    "hiring",
    "sales",
    "marketing",
    "operations",
    "management",
}
FIELD_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?$")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)
ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["SKILL.md must start with YAML frontmatter"]

    try:
        closing = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return {}, ["frontmatter is missing its closing ---"]

    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = FIELD_PATTERN.match(line)
        if not match:
            problems.append(f"invalid top-level frontmatter line: {line!r}")
            continue
        key, value = match.groups()
        fields[key] = (value or "").strip().strip("'\"")

    body = "\n".join(lines[closing + 1 :]).strip()
    if not body:
        problems.append("Markdown body must not be empty")
    if PLACEHOLDER_PATTERN.search(text):
        problems.append("unfinished placeholder found (TODO, TBD, or FIXME)")
    return fields, problems


def validate_skill(path: Path) -> list[str]:
    problems: list[str] = []
    relative = path.relative_to(ROOT)
    if path.parent.parent.parent != SKILLS_DIR:
        problems.append("skill must live at skills/<category>/<skill-name>/SKILL.md")
    elif path.parent.parent.name not in CATEGORIES:
        problems.append(f"unknown skill category: {path.parent.parent.name!r}")

    fields, parse_problems = parse_frontmatter(path)
    problems.extend(parse_problems)

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        problems.append("frontmatter requires a non-empty name")
    elif len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        problems.append("name must be <=64 characters of lowercase letters, digits, and hyphens")
    elif name != path.parent.name:
        problems.append(f"name {name!r} must match parent directory {path.parent.name!r}")

    if not description:
        problems.append("frontmatter requires a non-empty description")
    elif len(description) > 1024:
        problems.append("description must be <=1024 characters")

    license_name = fields.get("license")
    if license_name not in (None, "MIT"):
        problems.append("license must be MIT or omitted for this repository")

    return [f"{relative}: {problem}" for problem in problems]


def main() -> int:
    skill_files = sorted(SKILLS_DIR.glob("**/SKILL.md")) if SKILLS_DIR.exists() else []
    if not skill_files:
        print("No skills found yet; repository scaffold is valid.")
        return 0

    problems = [problem for path in skill_files for problem in validate_skill(path)]
    embedded_tests = sorted(SKILLS_DIR.glob("**/test_*.py"))
    problems.extend(
        f"{path.relative_to(ROOT)}: development tests must live under tests/"
        for path in embedded_tests
    )
    for category in sorted(CATEGORIES):
        category_dir = SKILLS_DIR / category
        keep_file = category_dir / ".gitkeep"
        if keep_file.exists() and any(path.name != ".gitkeep" for path in category_dir.iterdir()):
            problems.append(
                f"{keep_file.relative_to(ROOT)}: remove .gitkeep from a non-empty category"
            )
    if problems:
        print("Skill validation failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_files)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
