#!/usr/bin/env python3
"""Run every repository test file without third-party dependencies."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


def main() -> int:
    test_files = sorted(TESTS_DIR.glob("**/test_*.py"))
    if not test_files:
        print("No test files found.", file=sys.stderr)
        return 1

    failures: list[Path] = []
    for test_file in test_files:
        relative = test_file.relative_to(ROOT)
        print(f"\n==> {relative}", flush=True)
        completed = subprocess.run([sys.executable, str(test_file)], cwd=ROOT)
        if completed.returncode != 0:
            failures.append(relative)

    if failures:
        print("\nFailed test files:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"\nPassed {len(test_files)} test file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
