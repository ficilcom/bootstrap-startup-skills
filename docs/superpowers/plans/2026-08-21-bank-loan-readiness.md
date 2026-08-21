# Bank Loan Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable Japanese business-loan readiness Skill with separate startup and operating-company assessments, transparent evidence handling, deterministic scoring, and actionable reports.

**Architecture:** `SKILL.md` orchestrates document review, focused intake, mode-specific assessment, scoring, and reporting. Focused references hold the rubrics, red flags, lending-route guidance, and report contract, while a dependency-free Python CLI validates normalized JSON and calculates scores, confidence, readiness bands, provisional status, and caps deterministically.

**Tech Stack:** Agent Skills Markdown/YAML, Python 3.12+ standard library, `unittest`, JSON

**Spec:** `docs/superpowers/specs/2026-08-21-bank-loan-readiness-design.md`

## Global Constraints

- The public skill name is `bank-loan-readiness` at `skills/finance/bank-loan-readiness/`.
- Support startup mode and operating-company mode as separate rubrics.
- Scores measure application readiness from 0 to 100, never approval probability.
- Classify material information as `confirmed`, `reported`, `inferred`, or `unknown`.
- Unknown inputs earn no points but must not be described as adverse facts.
- Use current official sources for named programs, rates, thresholds, and lender-specific requirements.
- Do not submit applications, contact external parties, or expose unnecessary sensitive data.
- Use only Python's standard library in the scoring script and tests.
- The scoring result is provisional when confidence is below 60% or any mode-specific core criterion is unknown.
- A `major` red flag caps the score at 59; a `critical` red flag caps it at 39; the lowest applicable cap wins.

---

## File Map

- Create `skills/finance/bank-loan-readiness/scripts/calculate_score.py`: normalized input validation, weighted scoring, confidence, band, provisional status, and cap calculation.
- Create `tests/test_calculate_score.py`: unit and CLI tests for both modes and failure cases.
- Create `skills/finance/bank-loan-readiness/references/startup-rubric.md`: observable 0–5 anchors for startup assessment.
- Create `skills/finance/bank-loan-readiness/references/operating-company-rubric.md`: observable 0–5 anchors for established-company assessment.
- Create `skills/finance/bank-loan-readiness/references/red-flags.md`: factual thresholds, severity, cap behavior, and remediation prompts.
- Create `skills/finance/bank-loan-readiness/references/intake.md`: document-first intake and focused follow-up questions.
- Create `skills/finance/bank-loan-readiness/references/lending-routes.md`: durable route-fit guidance and current-source boundary.
- Create `skills/finance/bank-loan-readiness/references/report-format.md`: exact report ordering and evidence language.
- Create `skills/finance/bank-loan-readiness/SKILL.md`: short orchestrator and routing instructions.
- Modify `README.md`: add the published skill to a catalog and show its install command.

---

### Task 1: Deterministic Scoring Engine

**Files:**
- Create: `skills/finance/bank-loan-readiness/scripts/calculate_score.py`
- Create: `tests/test_calculate_score.py`

**Interfaces:**
- Consumes JSON object with `mode`, complete `criteria`, and optional `red_flags`.
- Produces JSON object with `mode`, `raw_score`, `final_score`, `confidence_percent`, `provisional`, `readiness_band`, `criterion_points`, `missing_core_criteria`, and `applied_cap`.
- Exposes `calculate(payload: dict[str, object]) -> dict[str, object]` and `main(argv: list[str] | None = None) -> int`.
- CLI accepts a JSON file path or `-` for standard input and writes one JSON object to standard output.

- [ ] **Step 1: Write the scoring and validation tests**

Create `tests/test_calculate_score.py` with `unittest`. Load the module from its file path so the skill does not need to be a Python package:

```python
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/finance/bank-loan-readiness/scripts/calculate_score.py"
SPEC = importlib.util.spec_from_file_location("calculate_score", SCRIPT)
assert SPEC and SPEC.loader
score_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score_module)


def startup_payload(rating: int = 5, evidence: str = "confirmed") -> dict[str, object]:
    return {
        "mode": "startup",
        "criteria": {
            "business_plan": {"rating": rating, "evidence": evidence},
            "funding_plan": {"rating": rating, "evidence": evidence},
            "repayment_capacity": {"rating": rating, "evidence": evidence},
            "founder_capability": {"rating": rating, "evidence": evidence},
            "compliance": {"rating": rating, "evidence": evidence},
            "documentation": {"rating": rating, "evidence": evidence},
        },
        "red_flags": [],
    }


class CalculateScoreTests(unittest.TestCase):
    def test_perfect_startup_is_ready_with_full_confidence(self) -> None:
        result = score_module.calculate(startup_payload())
        self.assertEqual(result["raw_score"], 100.0)
        self.assertEqual(result["final_score"], 100.0)
        self.assertEqual(result["confidence_percent"], 100.0)
        self.assertEqual(result["readiness_band"], "ready")
        self.assertFalse(result["provisional"])

    def test_operating_company_uses_operating_weights(self) -> None:
        payload = {
            "mode": "operating_company",
            "criteria": {
                "repayment_capacity": {"rating": 4, "evidence": "confirmed"},
                "financial_health": {"rating": 3, "evidence": "confirmed"},
                "business_viability": {"rating": 4, "evidence": "reported"},
                "borrowing_suitability": {"rating": 3, "evidence": "confirmed"},
                "compliance": {"rating": 5, "evidence": "reported"},
                "documentation": {"rating": 4, "evidence": "confirmed"},
            },
            "red_flags": [],
        }
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 76.0)
        self.assertEqual(result["readiness_band"], "conditionally_ready")
        self.assertEqual(result["confidence_percent"], 88.0)

    def test_major_and_critical_caps_use_lowest_cap(self) -> None:
        payload = startup_payload()
        payload["red_flags"] = [
            {"code": "tax_arrears", "severity": "major", "evidence": "reported"},
            {"code": "material_misrepresentation", "severity": "critical", "evidence": "confirmed"},
        ]
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 100.0)
        self.assertEqual(result["final_score"], 39.0)
        self.assertEqual(result["applied_cap"], 39)
        self.assertEqual(result["readiness_band"], "significant_issues")

    def test_unknown_core_criterion_is_zero_and_provisional(self) -> None:
        payload = startup_payload()
        payload["criteria"]["funding_plan"] = {"rating": 0, "evidence": "unknown"}
        result = score_module.calculate(payload)
        self.assertEqual(result["raw_score"], 80.0)
        self.assertTrue(result["provisional"])
        self.assertEqual(result["missing_core_criteria"], ["funding_plan"])

    def test_rejects_incomplete_criteria(self) -> None:
        payload = startup_payload()
        del payload["criteria"]["documentation"]
        with self.assertRaisesRegex(ValueError, "criteria must contain exactly"):
            score_module.calculate(payload)

    def test_rejects_out_of_range_rating(self) -> None:
        payload = startup_payload(rating=6)
        with self.assertRaisesRegex(ValueError, "rating"):
            score_module.calculate(payload)

    def test_rejects_unconfirmed_red_flag(self) -> None:
        payload = startup_payload()
        payload["red_flags"] = [
            {"code": "possible_arrears", "severity": "major", "evidence": "unknown"}
        ]
        with self.assertRaisesRegex(ValueError, "red flag evidence"):
            score_module.calculate(payload)

    def test_cli_returns_json(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(startup_payload(), handle)
            handle.flush()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), handle.name],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result["final_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test file and verify the missing-module failure**

Run:

```bash
python3 -m unittest tests/test_calculate_score.py -v
```

Expected: FAIL while importing the missing `calculate_score.py` file.

- [ ] **Step 3: Implement the scoring module constants and validation**

Create `calculate_score.py` with these exact public constants and helpers:

```python
MODE_CONFIG = {
    "startup": {
        "weights": {
            "business_plan": 25,
            "funding_plan": 20,
            "repayment_capacity": 20,
            "founder_capability": 15,
            "compliance": 15,
            "documentation": 5,
        },
        "core": {"funding_plan", "repayment_capacity", "compliance"},
    },
    "operating_company": {
        "weights": {
            "repayment_capacity": 30,
            "financial_health": 20,
            "business_viability": 15,
            "borrowing_suitability": 15,
            "compliance": 15,
            "documentation": 5,
        },
        "core": {
            "repayment_capacity",
            "financial_health",
            "borrowing_suitability",
            "compliance",
        },
    },
}

EVIDENCE_FACTORS = {"confirmed": 1.0, "reported": 0.6, "inferred": 0.3, "unknown": 0.0}
CAPS = {"major": 59, "critical": 39}


def readiness_band(score: float) -> str:
    if score >= 80:
        return "ready"
    if score >= 65:
        return "conditionally_ready"
    if score >= 50:
        return "improvement_priority"
    return "significant_issues"
```

Validation must require a known mode, exactly the expected criterion keys, numeric non-boolean ratings from 0 through 5, known evidence values, a list of red flags, known red-flag severity, and `confirmed` or `reported` evidence for every applied red flag. Raise `ValueError` with the failing field in the message.

- [ ] **Step 4: Implement calculation and the JSON CLI**

Implement `calculate(payload)` so each criterion contributes `weight * rating / 5`. Confidence contributes `weight * EVIDENCE_FACTORS[evidence]`; because weights total 100, the sum is already a percentage. Determine missing core criteria from core entries whose evidence is `unknown`. Set `provisional` when confidence is below 60 or this list is non-empty. Apply the lowest red-flag cap after calculating the raw score.

Implement `main()` with `argparse`: read from the provided path or `sys.stdin` for `-`, emit UTF-8 JSON to standard output, and convert `ValueError`, malformed JSON, and file errors into a concise `error: ...` message on standard error with exit code 2.

- [ ] **Step 5: Run the scoring tests**

Run:

```bash
python3 -m unittest tests/test_calculate_score.py -v
```

Expected: all eight tests PASS.

- [ ] **Step 6: Commit the scoring engine**

```bash
git add skills/finance/bank-loan-readiness/scripts/calculate_score.py tests/test_calculate_score.py
git commit -m "feat: add deterministic loan readiness scoring"
```

---

### Task 2: Mode-Specific Rubrics and Red Flags

**Files:**
- Create: `skills/finance/bank-loan-readiness/references/startup-rubric.md`
- Create: `skills/finance/bank-loan-readiness/references/operating-company-rubric.md`
- Create: `skills/finance/bank-loan-readiness/references/red-flags.md`

**Interfaces:**
- Consumes the normalized criterion IDs defined by `MODE_CONFIG`.
- Produces one 0–5 rating, one evidence classification, concise evidence, and rationale for every criterion.
- Produces red flags shaped as `{"code": str, "severity": "major" | "critical", "evidence": "confirmed" | "reported"}` for the scoring script.

- [ ] **Step 1: Write the startup rubric**

For each startup criterion, include its exact ID and weight, the facts to inspect, and observable anchors for ratings 0, 1, 3, and 5. State that 2 and 4 are used only when evidence falls materially between adjacent anchors. Cover these required anchors:

- `business_plan`: customer problem, offering, target market, acquisition path, supplier or operating assumptions, and externally supportable sales logic.
- `funding_plan`: itemized startup and working-capital needs, quotes or calculation support, owner funding provenance, total sources equal total uses, and reasonable borrowing dependence.
- `repayment_capacity`: monthly sales, cost and expense basis, owner living costs where relevant, taxes, existing payments, requested payments, downside case, and residual cash.
- `founder_capability`: relevant industry and management experience, licenses, execution evidence, gaps, and mitigation.
- `compliance`: taxes, social insurance, personal or business repayment history as voluntarily disclosed, required permits, and consistency of declarations.
- `documentation`: availability, recency, internal consistency, and ability to explain material assumptions.

Do not encode a universal minimum owner-funding ratio. Treat owner funding as one factor whose context and provenance matter.

- [ ] **Step 2: Write the operating-company rubric**

For each operating-company criterion, include its exact ID and weight, the facts to inspect, and observable anchors for ratings 0, 1, 3, and 5. Cover:

- `repayment_capacity`: normalized operating cash generation, existing and proposed annual debt service, working-capital seasonality, downside resilience, and reconciliation to supplied statements.
- `financial_health`: revenue and profit trend, net assets, liquidity, leverage, receivable and inventory quality, related-party balances, and one-off normalization.
- `business_viability`: customer concentration, recurring demand, competitive position, management capability, operational dependencies, and forward evidence.
- `borrowing_suitability`: itemized use, requested amount, timing, term-to-asset-life alignment, sources and uses, and alternative funding.
- `compliance`: taxes, social insurance, repayment history, existing borrowing terms, licenses, and material legal or regulatory matters.
- `documentation`: completed financial statements, current trial balance, debt schedule, cash-flow information, recency, consistency, and management explanation.

The rubric may calculate supporting ratios but must not claim a universal lender cutoff. Explain that industry, stage, lender, collateral, guarantee, and transaction structure affect interpretation.

- [ ] **Step 3: Write the red-flag reference**

Define codes, severity, evidence requirements, why each matters, clarifying questions, and remediation. Include at least:

| Code | Default severity |
| --- | --- |
| `current_serious_delinquency` | critical |
| `material_misrepresentation` | critical |
| `ineligible_or_illegal_use` | critical |
| `missing_required_license` | critical when operation is unlawful; otherwise major |
| `tax_or_social_insurance_arrears` | major |
| `unsupported_debt_service` | major |
| `unexplained_material_inconsistency` | major |
| `unclear_use_of_funds` | major |

Require `confirmed` or `reported` evidence before sending a red flag to the script. Keep `unknown` or `inferred` concerns in an unresolved-questions list. State that the caps describe readiness and do not encode automatic lender rejection.

- [ ] **Step 4: Check criterion IDs and placeholder-free content**

Run:

```bash
rg -n "business_plan|funding_plan|repayment_capacity|founder_capability|financial_health|business_viability|borrowing_suitability|compliance|documentation" skills/finance/bank-loan-readiness/references
rg -n "TO[D]O|T[B]D|FIX[M]E" skills/finance/bank-loan-readiness/references
```

Expected: every mode-specific criterion appears in its rubric; the placeholder scan returns no matches.

- [ ] **Step 5: Commit the rubrics**

```bash
git add skills/finance/bank-loan-readiness/references/startup-rubric.md skills/finance/bank-loan-readiness/references/operating-company-rubric.md skills/finance/bank-loan-readiness/references/red-flags.md
git commit -m "feat: define Japanese loan readiness rubrics"
```

---

### Task 3: Intake, Lending Routes, and Report Contract

**Files:**
- Create: `skills/finance/bank-loan-readiness/references/intake.md`
- Create: `skills/finance/bank-loan-readiness/references/lending-routes.md`
- Create: `skills/finance/bank-loan-readiness/references/report-format.md`

**Interfaces:**
- Intake produces the mode, evidence inventory, material conflicts, criterion evidence, and unresolved questions.
- Lending routes consume completed assessment findings and produce broad route-fit tendencies without stale program claims.
- Report format consumes the scorer JSON plus narrative evidence and produces the ordered diagnostic report from the spec.

- [ ] **Step 1: Write document-first intake guidance**

Create `intake.md` with:

1. jurisdiction and assessment-scope confirmation;
2. mode selection using business start date and presence of a completed fiscal year;
3. a shared document inventory;
4. startup-specific documents and questions;
5. operating-company documents and questions;
6. conflict handling and sensitive-data minimization;
7. a stopping rule for follow-up questions.

Startup materials include the startup plan, founder history, funding and use-of-funds schedule, quotations, owner-funding evidence, monthly forecast, existing debt, permits, and tax or social-insurance status where applicable. Operating-company materials include up to three completed periods when available, current trial balance, debt schedule, cash-flow or bank movement information, tax filings, receivable and inventory detail where material, requested-use support, and current forecast.

Ask only questions that can change a criterion rating, evidence status, red-flag determination, lending-route fit, or recommended action. Stop when remaining unknowns would not materially change the result, or the user declines further disclosure.

- [ ] **Step 2: Write durable lending-route guidance**

Create `lending-routes.md` comparing:

- Japan Finance Corporation, especially startup or small-business contexts;
- credit-guarantee-backed lending through a private financial institution;
- conventional direct lending from banks, credit unions, or credit associations.

For each route, state the situations that tend to fit, evidence that strengthens the case, limitations, and facts that require current official verification. Do not hard-code rates, limits, guarantee percentages, named local programs, or temporary eligibility rules. Link the stable official sources listed in the design spec and direct the agent to jurisdiction-specific guarantee-association and lender pages when making concrete claims.

- [ ] **Step 3: Write the exact report template**

Create `report-format.md` with these headings and required fields:

```markdown
# 融資申請準備度診断

## 診断概要
- 診断日
- 診断モード
- 対象となる借入目的・希望額
- 判定の前提

## 総合結果
- 総合判定
- 申請準備度: __ / 100
- 診断確度: __%
- 暫定判定: はい / いいえ

## 項目別評価
| 項目 | 得点 / 配点 | 情報区分 | 主な根拠 | 評価理由 |

## 強み
## 重大懸念
## 未解決の重要確認事項
## 優先改善アクション
| 優先度 | 対応 | 理由 | 完了の目安 |

## 不足資料
## 適合傾向のある融資ルート
## 次の行動
## 注意事項
```

Require the readiness-band label next to the score, applied caps next to confirmed red flags, and missing core criteria next to any provisional score. Include exact language that the score is readiness, not approval probability, and that named program details require current official verification.

- [ ] **Step 4: Review the references against the report contract**

Run:

```bash
rg -n "confirmed|reported|inferred|unknown|暫定|申請準備度|診断確度" skills/finance/bank-loan-readiness/references
rg -n "TO[D]O|T[B]D|FIX[M]E" skills/finance/bank-loan-readiness/references
```

Expected: evidence states and report labels are discoverable; the placeholder scan returns no matches.

- [ ] **Step 5: Commit the intake and output contract**

```bash
git add skills/finance/bank-loan-readiness/references/intake.md skills/finance/bank-loan-readiness/references/lending-routes.md skills/finance/bank-loan-readiness/references/report-format.md
git commit -m "feat: add loan readiness intake and report guidance"
```

---

### Task 4: Skill Orchestration and Repository Discovery

**Files:**
- Create: `skills/finance/bank-loan-readiness/SKILL.md`
- Modify: `README.md`

**Interfaces:**
- `SKILL.md` routes to exactly the references needed for the selected mode and invokes `scripts/calculate_score.py` with normalized JSON.
- README exposes the install name `bank-loan-readiness` to repository users.

- [ ] **Step 1: Write the SKILL.md frontmatter and boundaries**

Use this frontmatter:

```yaml
---
name: bank-loan-readiness
description: Assess how ready a Japan-based founder or small business is to apply for a business loan, using available plans and financial documents plus focused follow-up questions. Use for pre-application diagnosis, weakness identification, and improvement planning for startup or operating-company borrowing; do not use the score as an approval prediction.
license: MIT
metadata:
  author: ficilcom
---
```

Open the body with the outcome, Japan-only scope, readiness-not-probability boundary, and requirement to distinguish evidence states.

- [ ] **Step 2: Write the orchestration workflow**

Keep `SKILL.md` under 250 lines. It must instruct the agent to:

1. read `references/intake.md` and determine mode;
2. inspect supplied documents before asking questions;
3. read only the selected mode rubric plus `references/red-flags.md`;
4. normalize all expected criteria with rating, evidence state, and rationale;
5. create scorer input outside the skill directory, minimizing sensitive data;
6. run `scripts/calculate_score.py <input.json>` and stop on validation errors;
7. read `references/lending-routes.md` and `references/report-format.md`;
8. produce the Japanese report and clearly mark provisional results;
9. research current official sources only when concrete programs or current conditions are requested;
10. ask for authorization before any application, external contact, or submission.

Link every reference directly from `SKILL.md`. Do not copy the detailed rubrics into the entrypoint.

- [ ] **Step 3: Add the skill to README**

Add an `Available skills` table containing:

```markdown
| Skill | Description |
| --- | --- |
| [`bank-loan-readiness`](skills/finance/bank-loan-readiness/) | Assess application readiness for Japanese startup and operating-company loans, identify weaknesses, and prioritize improvements. |
```

Add the specific install example:

```bash
npx skills add ficilcom/bootstrap-startup-skills \
  --skill bank-loan-readiness \
  --agent codex \
  --global
```

- [ ] **Step 4: Run structural validation and scoring tests**

Run:

```bash
python3 scripts/validate_skills.py
python3 -m unittest tests/test_calculate_score.py -v
git diff --check
```

Expected: the repository validator reports one valid skill, all scoring tests pass, and the diff check is silent.

- [ ] **Step 5: Commit the public skill**

```bash
git add skills/finance/bank-loan-readiness/SKILL.md README.md
git commit -m "feat: add bank loan readiness skill"
```

---

### Task 5: End-to-End Verification

**Files:**
- Modify only if verification exposes a demonstrated defect in the files created by Tasks 1–4.

**Interfaces:**
- Consumes the completed skill and two realistic assessment scenarios.
- Produces evidence that mode routing, normalized scoring, provisional handling, red-flag separation, and report structure work together.

- [ ] **Step 1: Run a startup scorer scenario**

Create a temporary JSON file outside the repository with all six startup criteria, mixed `confirmed` and `reported` evidence, no red flags, and ratings that yield a score between 65 and 79. Run:

```bash
python3 skills/finance/bank-loan-readiness/scripts/calculate_score.py /tmp/bank-loan-startup.json
```

Expected: `mode` is `startup`, the score is in the conditional band, confidence follows the evidence factors, and the result is not provisional when core criteria are known and confidence is at least 60%.

- [ ] **Step 2: Run an operating-company red-flag scenario**

Create a temporary JSON file with all six operating-company criteria, a raw score above 65, and a confirmed `critical` red flag. Run:

```bash
python3 skills/finance/bank-loan-readiness/scripts/calculate_score.py /tmp/bank-loan-operating.json
```

Expected: `raw_score` remains above 65, `final_score` is 39, `applied_cap` is 39, and the readiness band is `significant_issues`.

- [ ] **Step 3: Exercise the Skill with two realistic user requests**

Use an isolated temporary workspace and run one request for a pre-launch founder with a startup plan and one request for an operating company with financial statements. Inspect the resulting reports for:

- correct mode selection;
- questions limited to material missing facts;
- all facts labeled by evidence status;
- scorer output reproduced accurately;
- confirmed red flags separated from unresolved questions;
- the exact report sections in `report-format.md`;
- no claim of approval probability;
- no unsourced current program details.

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
git diff --check
rg -n "TO[D]O|T[B]D|FIX[M]E" skills/finance/bank-loan-readiness tests
```

Expected: validation and all tests pass, diff check is silent, and the placeholder scan returns no matches.

- [ ] **Step 5: Commit verification-supported corrections, if any**

If Step 3 exposed a defect, add only the affected Skill or test files and commit:

```bash
git add skills/finance/bank-loan-readiness tests
git commit -m "fix: refine bank loan readiness behavior"
```

If no defect was found, do not create an empty commit.
