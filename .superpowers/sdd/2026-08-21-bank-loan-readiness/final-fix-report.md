# Bank Loan Readiness — Final Fix Report

Date: 2026-08-21
Branch: `feature/bank-loan-readiness`
Planned commit subject: `fix: finalize bank loan readiness contracts`

## Scope and exact files changed

1. `skills/finance/bank-loan-readiness/SKILL.md`
2. `skills/finance/bank-loan-readiness/references/lending-routes.md`
3. `skills/finance/bank-loan-readiness/references/red-flags.md`
4. `skills/finance/bank-loan-readiness/scripts/calculate_score.py`
5. `tests/test_calculate_score.py`
6. `.superpowers/sdd/2026-08-21-bank-loan-readiness/final-fix-report.md`

The pre-existing untracked `.superpowers/sdd-tools/` directory was not changed or staged.

## Resolution of the five Important findings

### 1. Red-flag contract validation

- Added an explicit `RED_FLAG_SEVERITIES` catalog covering all eight documented codes.
- Validation now requires `code` to be a nonempty string present in the catalog.
- Validation now rejects code/severity combinations outside the catalog.
- `missing_required_license` alone accepts both `major` and `critical`; every other code accepts its single documented severity.
- Existing test fixtures now use the documented `tax_or_social_insurance_arrears` code instead of nonexistent `tax_arrears` or `possible_arrears` codes.
- Added tests for unknown, empty, and non-string codes; severity mismatches; both license severities; and the complete documented code/severity mapping.

### 2. Integer rating and score-reconciliation contract

- The scorer now accepts only non-boolean integers from 0 through 5. Floats such as `1.234` and `3.0`, plus booleans, are rejected.
- The Skill entrypoint now states that `rating` is an integer from 0 through 5, matching both rubrics.
- Removed the prior fractional-rating behavior test.
- `raw_score` is now calculated as the one-decimal sum of the already rounded, displayed `criterion_points`, so the report total reconciles structurally.
- Added a mixed-rating reconciliation invariant test.

### 3. Durable official links

Replaced the dead or year-pinned links in `references/lending-routes.md` with durable official landing pages:

- Japan Finance Corporation, “創業計画の書き方”: <https://www.jfc.go.jp/n/finance/sougyou/business-plan/>
- Japan Finance Corporation, “創業計画書セルフチェック”: <https://www.jfc.go.jp/n/finance/sougyou/sougyouselfchek/>
- Tokyo Credit Guarantee Association, “ディスクロージャー誌”: <https://www.cgc-tokyo.or.jp/about/profile/disclosure.html>

No current rate, limit, guarantee percentage, or time-sensitive eligibility rule was embedded.

Official-link verification on 2026-08-21 used direct page opens:

- The JFC business-plan URL resolved as HTML titled “創業計画の書き方” and contained the plan download, FAQ/video guidance, funding-plan, and income/expense-plan sections.
- The JFC self-check URL resolved as HTML titled “創業計画書セルフチェック” and described pre-application plan review, with a self-check start link and checklist resources.
- The Tokyo CGC URL resolved as HTML titled “ディスクロージャー誌” and listed annual disclosure reports, including 2026 and prior years. This confirms it is the durable index rather than a year-specific PDF.

### 4. `unsupported_debt_service` evidence boundary

The flag now applies only when confirmed or reported cash-flow evidence shows insufficient coverage, or the applicant confirms that no substantive repayment basis or model exists. The reference explicitly says unavailable support documents alone remain `unknown` and unresolved and do not establish the flag.

### 5. Required regression and contract tests

Added table-driven readiness-band tests immediately below, at, and immediately above the 50, 65, and 80 boundaries; identical-input determinism; confidence exactly 60%; core-unknown and non-core-unknown provisional behavior; criterion ID/weight behavior; the full documented red-flag mapping; and the raw-score reconciliation invariant.

## TDD evidence

The contract tests were written before the production changes. The expected production changes were:

- integer-only rating validation would make fractional and float ratings fail;
- code validation would reject unknown, empty, and non-string codes;
- catalog validation would reject valid codes paired with the wrong severity.

RED command:

```bash
python3 -m unittest -v tests.test_calculate_score.CalculateScoreTests.test_rejects_non_integer_ratings tests.test_calculate_score.CalculateScoreTests.test_rejects_unknown_or_invalid_red_flag_code tests.test_calculate_score.CalculateScoreTests.test_rejects_red_flag_severity_that_conflicts_with_catalog
```

Observed output (exit 1):

```text
test_rejects_non_integer_ratings ... FAIL (3 subtest failures)
test_rejects_unknown_or_invalid_red_flag_code ... FAIL (3 subtest failures)
test_rejects_red_flag_severity_that_conflicts_with_catalog ... FAIL (2 subtest failures)
Ran 3 tests in 0.001s
FAILED (failures=8)
```

The failures were for the intended missing behavior: fractional ratings raised no error; the boolean error did not yet state the integer contract; invalid codes raised no error; and mismatched catalog severities raised no error.

GREEN command after the minimal scorer change:

```bash
python3 -m unittest -v tests.test_calculate_score
```

Observed output after the final compact mapping test was added (exit 0):

```text
Ran 19 tests in 0.045s
OK
```

## Realistic scorer scenarios

### Startup

Command:

```bash
python3 skills/finance/bank-loan-readiness/scripts/calculate_score.py /tmp/bank-loan-startup.json
```

Input used integer ratings and no red flags. Exact output (exit 0):

```json
{"mode":"startup","raw_score":68.0,"final_score":68.0,"confidence_percent":78.0,"provisional":false,"readiness_band":"conditionally_ready","criterion_points":{"business_plan":20.0,"funding_plan":12.0,"repayment_capacity":12.0,"founder_capability":12.0,"compliance":9.0,"documentation":3.0},"missing_core_criteria":[],"applied_cap":null}
```

The displayed points sum to 68.0, matching `raw_score`; all core criteria are known and confidence exceeds 60%, so the result is not provisional.

### Operating company

Command:

```bash
python3 skills/finance/bank-loan-readiness/scripts/calculate_score.py /tmp/bank-loan-operating.json
```

The input used the documented `current_serious_delinquency` / `critical` combination. Exact output (exit 0):

```json
{"mode":"operating_company","raw_score":85.0,"final_score":39,"confidence_percent":100.0,"provisional":false,"readiness_band":"significant_issues","criterion_points":{"repayment_capacity":30.0,"financial_health":20.0,"business_viability":15.0,"borrowing_suitability":15.0,"compliance":0.0,"documentation":5.0},"missing_core_criteria":[],"applied_cap":39}
```

The displayed points sum to 85.0, matching `raw_score`; the valid critical flag applies the 39 cap and the final band is `significant_issues`.

## Final verification evidence

Focused suite:

```bash
python3 -m unittest -v tests.test_calculate_score
```

Output (exit 0):

```text
Ran 19 tests in 0.045s
OK
```

Full repository test suite:

```bash
python3 -m unittest discover -s tests -v
```

Output (exit 0):

```text
test_cli_returns_json ... ok
test_confidence_exactly_sixty_is_not_provisional ... ok
test_criterion_ids_and_weights_drive_scores ... ok
test_documented_red_flag_code_severity_mapping ... ok
test_identical_inputs_produce_identical_outputs ... ok
test_major_and_critical_caps_use_lowest_cap ... ok
test_missing_license_accepts_both_catalog_severities ... ok
test_operating_company_uses_operating_weights ... ok
test_perfect_startup_is_ready_with_full_confidence ... ok
test_raw_score_reconciles_to_displayed_criterion_points ... ok
test_readiness_band_boundaries ... ok
test_rejects_incomplete_criteria ... ok
test_rejects_non_integer_ratings ... ok
test_rejects_out_of_range_rating ... ok
test_rejects_red_flag_severity_that_conflicts_with_catalog ... ok
test_rejects_unconfirmed_red_flag ... ok
test_rejects_unknown_or_invalid_red_flag_code ... ok
test_unknown_core_criterion_is_zero_and_provisional ... ok
test_unknown_non_core_criterion_does_not_make_result_provisional ... ok
Ran 19 tests in 0.031s
OK
```

Skill validator:

```bash
python3 scripts/validate_skills.py
```

Exact output (exit 0):

```text
Validated 1 skill(s).
```

Whitespace/error check:

```bash
git diff --check
```

Exact output: none (exit 0).

Placeholder scan:

```bash
rg -n "TO[D]O|T[B]D|FIX[M]E" skills/finance/bank-loan-readiness tests
```

Exact output: none (exit 1, the expected no-match status).

## Self-review

- Compared the scorer catalog against every heading and severity in `references/red-flags.md`: all eight codes match, all fixed severities match, and only `missing_required_license` has two allowed severities.
- Confirmed code validation happens before severity and evidence validation, so malformed or unknown codes cannot reach cap selection.
- Confirmed boolean values are rejected despite Python treating `bool` as an `int` subclass.
- Confirmed all rating calculations use the validated integer values and `raw_score` is sourced from displayed criterion contributions.
- Confirmed boundary expectations match the design: 0–49, 50–64, 65–79, and 80–100.
- Confirmed confidence exactly 60% is not provisional because the contract is “below 60%”; a known non-core omission alone does not make a sufficiently confident score provisional, while a core omission does.
- Confirmed the route reference contains durable landing pages and no current rates or limits.
- Confirmed missing repayment-support documents cannot, by wording alone, become a major flag.
- Reviewed the complete diff and found no unrelated tracked changes.

## Concerns

No functional concern remains within the requested fix scope. The pre-existing untracked `.superpowers/sdd-tools/` directory remains untouched and will not be included in the commit.
