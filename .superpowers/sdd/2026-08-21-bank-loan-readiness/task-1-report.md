# Task 1 report: deterministic scoring engine

## What was implemented

- Added `calculate_score.py` with the required startup and operating-company weight configurations, evidence factors, readiness bands, red-flag caps, validation, deterministic scoring, confidence and provisional status calculation, and CLI JSON input/output.
- Added eight `unittest` tests covering perfect startup scoring, operating-company weights, lowest red-flag cap, unknown core criteria, validation failures, and the file-based CLI.

## Tests and exact results

Focused command:

```text
python3 -m unittest tests/test_calculate_score.py -v
Ran 8 tests in 0.034s
OK
```

Repository validation:

```text
python3 scripts/validate_skills.py
No skills found yet; repository scaffold is valid.
```

An unqualified discovery run (`python3 -m unittest discover -v`) found no tests because this repository's tests directory is not an importable discovery package; it exited 5 with `Ran 0 tests`.

## TDD RED

Command:

```text
python3 -m unittest tests/test_calculate_score.py -v
```

Expected failure occurred while importing the deliberately missing module:

```text
FileNotFoundError: [Errno 2] No such file or directory: '.../skills/finance/bank-loan-readiness/scripts/calculate_score.py'
```

This was expected because the tests were written before the scoring implementation.

## TDD GREEN

After implementing the module, the same focused command passed all eight tests (`Ran 8 tests ... OK`).

## Files changed

- `skills/finance/bank-loan-readiness/scripts/calculate_score.py`
- `tests/test_calculate_score.py`
- This report file.

## Self-review findings

- Validation rejects unknown modes, incorrect criterion sets, invalid/non-numeric/boolean ratings, unknown evidence, malformed red-flag lists, unknown severities, and non-confirmed/non-reported red-flag evidence.
- Scores and confidence are rounded to two decimal places; caps are applied after raw scoring and the lowest cap wins.
- CLI errors are concise, sent to stderr, and return exit code 2.

## Concerns

- `python3 -m unittest discover -v` does not discover tests in this scaffold (0 tests, exit 5); the explicitly required focused command passes all eight tests.

## Fix Round 1

### What changed

- Unknown-evidence criteria now contribute zero criterion points regardless of their supplied rating.
- Criterion points, raw score, confidence percentage, and final score now use one-decimal-place arithmetic.
- Added coverage for a nonzero rating with unknown evidence and for fractional one-decimal rounding.

### Covering tests and exact results

The new test-first command initially failed as expected: the unknown-evidence case returned `raw_score` 100.0 instead of 80.0, and the fractional case returned 6.17 instead of 6.2.

```text
python3 -m unittest tests/test_calculate_score.py -v
Ran 9 tests in 0.036s
OK
```

```text
python3 scripts/validate_skills.py
No skills found yet; repository scaffold is valid.
```
