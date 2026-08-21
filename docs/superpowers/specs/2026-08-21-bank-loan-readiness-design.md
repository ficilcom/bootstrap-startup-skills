# Bank Loan Readiness Skill Design

## Purpose

Create a portable Agent Skill that helps founders and small or medium-sized businesses in Japan assess their readiness before applying for a business loan. The skill identifies strengths, weaknesses, missing evidence, and prioritized improvements. It does not predict approval probability or replace a lender, accountant, tax adviser, or attorney.

The public skill name is `bank-loan-readiness`, located at `skills/finance/bank-loan-readiness/`.

## Scope

The skill supports two explicitly separated modes:

1. **Startup mode** for businesses before launch or without a complete first fiscal year.
2. **Operating-company mode** for businesses with at least one completed fiscal year.

It supports both document-led and interview-led assessment. Available documents are reviewed first; the agent asks only for material information that remains missing. A user can still complete a provisional assessment without documents.

The standard output includes broad fit with these lending routes:

- Japan Finance Corporation;
- credit-guarantee-backed lending;
- conventional bank or credit-union lending, including the tendency toward direct lending where appropriate.

Named programs, current eligibility thresholds, rates, and lender-specific requirements are outside the static rubric. When requested, the agent must verify them against current official sources.

## Diagnostic Flow

1. Confirm that the business and requested assessment are in Japan.
2. Select startup or operating-company mode using business age and availability of completed financial statements.
3. Inventory available documents and extract relevant facts.
4. Classify information as document-confirmed, user-reported, inferred, or unknown.
5. Ask focused follow-up questions for material unknowns.
6. Evaluate each criterion against the mode-specific rubric and record evidence and rationale.
7. Pass criterion ratings and applicable red flags to a deterministic scoring script.
8. Produce the readiness report, clearly distinguishing adverse facts from missing evidence.
9. Describe suitable lending-route tendencies and prioritized next actions.
10. Research current official information only when specific programs or requirements are requested.

The agent must not fabricate missing values, treat estimates as facts, or submit an application or contact an external party without explicit authorization.

## Information Model

Every material input is labeled as one of:

- `confirmed`: supported by a supplied document;
- `reported`: stated by the user but not independently verified;
- `inferred`: calculated or inferred by the agent and disclosed as such;
- `unknown`: not available.

Unknown information earns no readiness points. This reflects incomplete application preparation, but the report must not describe an unknown as an adverse fact. The report separately displays diagnostic confidence so readers can distinguish weak readiness from limited evidence.

## Startup-Mode Scoring

| Criterion | Weight |
| --- | ---: |
| Business-plan specificity and feasibility | 25 |
| Funding plan, owner funding, and use of funds | 20 |
| Revenue forecast and repayment capacity | 20 |
| Founder experience and execution capability | 15 |
| Credit, tax, and legal or regulatory standing | 15 |
| Documentation and consistency of explanation | 5 |
| **Total** | **100** |

## Operating-Company Scoring

| Criterion | Weight |
| --- | ---: |
| Cash flow and repayment capacity | 30 |
| Financial health and performance trend | 20 |
| Business continuity and future viability | 15 |
| Suitability of amount, use, and repayment term | 15 |
| Existing debt, credit, tax, and legal or regulatory standing | 15 |
| Documentation and management explanation | 5 |
| **Total** | **100** |

Each criterion receives a rubric rating from 0 to 5: 0 is absent or severely deficient, 1 is very weak, 2 is weak, 3 is adequate with material gaps, 4 is strong, and 5 is strong and well supported. The mode-specific references define observable anchors for these ratings. The script calculates `weight * rating / 5`, sums the results, applies any red-flag cap, and rounds to one decimal place. It returns the raw total, final total, applied caps, confidence, and criterion-level point contributions in machine-readable output.

## Readiness Bands

| Score | Interpretation |
| ---: | --- |
| 80–100 | Ready to apply |
| 65–79 | Potentially ready with conditions |
| 50–64 | Prioritize improvements before applying |
| 0–49 | Resolve significant issues first |

These bands describe application readiness, not approval likelihood.

## Diagnostic Confidence

Diagnostic confidence is reported separately from readiness. Each criterion receives one evidence classification based on the material evidence supporting its rating. The scoring factors are `confirmed = 1.0`, `reported = 0.6`, `inferred = 0.3`, and `unknown = 0`. The script calculates confidence as the weighted sum of these factors across the mode's criteria and reports it as a percentage.

The report labels the result provisional when confidence is below 60% or a core criterion is `unknown`. Startup-mode core criteria are the funding plan and repayment-capacity criteria. Operating-company core criteria are repayment capacity, financial health, and suitability of the requested borrowing. Credit, tax, and legal or regulatory standing is core in both modes.

The skill may report a provisional numerical readiness score, but must display the provisional label and missing core inputs adjacent to the score.

## Red Flags and Score Caps

The rubric includes unresolved material concerns such as:

- tax or social-insurance arrears;
- significant current or recent repayment delinquency;
- unclear, unsupported, or ineligible use of funds;
- material inconsistencies between documents and explanations;
- missing licenses or legal ability to operate where required;
- repayment projections that do not support the requested debt service.

Red flags apply transparent score caps rather than asserting automatic rejection. A `major` red flag caps the score at 59, while a `critical` red flag caps it at 39. If several flags apply, the lowest cap wins. The red-flag reference defines the severity for each condition and requires a documented or user-confirmed factual basis. Each applied cap must identify the observed fact, evidence status, consequence, and action needed to resolve or clarify it. Unknown conditions are listed for confirmation and are not treated as confirmed red flags.

## Components

```text
skills/finance/bank-loan-readiness/
├── SKILL.md
├── references/
│   ├── intake.md
│   ├── startup-rubric.md
│   ├── operating-company-rubric.md
│   ├── red-flags.md
│   ├── lending-routes.md
│   └── report-format.md
└── scripts/
    └── calculate_score.py
```

`SKILL.md` orchestrates mode selection, evidence collection, scoring, and reporting. References contain conditional detail and are loaded only when relevant. `calculate_score.py` performs arithmetic and cap application but does not interpret business evidence.

## Report Contract

The final report contains, in order:

1. assessment mode, date, and scope;
2. overall readiness band;
3. readiness score, including a provisional label when applicable;
4. diagnostic confidence and evidence limitations;
5. criterion-level scores, evidence status, and rationale;
6. strengths;
7. confirmed red flags and unresolved critical questions;
8. prioritized improvements;
9. missing documents and information;
10. lending-route fit;
11. next actions;
12. limitations and professional-advice notice.

The report must keep confirmed red flags separate from unresolved questions. Recommendations should be ordered by their likely impact on readiness and practical sequence, not merely by point value.

## Source Policy

The durable rubric is grounded in stable official lending principles, including funding purpose, repayment capacity, business feasibility, owner preparation, management capability, and consistency of evidence. Initial authoritative references include:

- [Japan Finance Corporation: Startup Plan Q&A](https://www.jfc.go.jp/n/finance/sougyou/sougyou02.html)
- [Japan Finance Corporation: Startup Plan Self-Check](https://www.jfc.go.jp/n/finance/sougyou/sougyouselfchek/page_3/)
- [Tokyo Credit Guarantee Association disclosure report](https://www.cgc-tokyo.or.jp/about/profile/disclosure.files/cgc_tokyo2025.pdf)
- [Financial Services Agency: Cash-flow-based and business-value lending](https://www.fsa.go.jp/access/r7/274.html)

Time-sensitive program details must be researched when needed and must not be embedded as durable facts in the scoring rubric.

## Error Handling and Safety

- If supplied files cannot be read, identify the affected files and continue with available evidence or questions.
- If arithmetic inputs are invalid, the scoring script exits with a clear error and produces no misleading score.
- If a mode cannot be selected, ask for the business start date and whether a completed fiscal year exists.
- If evidence conflicts, surface the conflict and request clarification; do not select the more favorable value.
- Minimize reproduction of account numbers, personal identifiers, and other sensitive data in the report.
- Never claim that a score guarantees approval or reflects a lender's internal rating.

## Verification

Verification includes:

- repository and Agent Skills structure validation;
- unit tests for both scoring modes, boundary scores, unknown criteria, invalid inputs, and red-flag caps;
- at least one realistic startup case and one operating-company case;
- confirmation that identical normalized inputs produce identical scores;
- confirmation that missing information, adverse facts, and red flags remain distinct in the report;
- confirmation that specific current programs trigger official-source research rather than relying on embedded stale details.
