# Operating-company loan-readiness rubric

Use this rubric only with `mode: "operating_company"`. For every criterion, produce a JSON-ready assessment with `rating` (an integer from 0 through 5), `evidence` (`confirmed`, `reported`, `inferred`, or `unknown`), concise evidence, and a rationale. A rating measures readiness, not credit approval.

Supporting ratios can inform the analysis, but there is no universal lender cutoff. Industry, operating stage, lender, collateral, guarantee, and transaction structure affect interpretation. Keep source documents, management reports, and estimates distinguishable.

## `repayment_capacity` — weight 30

**Inspect:** normalized operating cash generation; existing and proposed annual debt service; working-capital seasonality; downside resilience; and reconciliation to supplied statements.

| Rating | Observable anchor |
| --- | --- |
| 0 | Operating cash generation and debt-service obligations cannot be established or plainly cannot support requested payments. |
| 1 | Repayment depends on unsubstantiated forecasts, omits debt or seasonal cash needs, or cannot be reconciled to supplied statements. |
| 3 | Normalized operating cash generation and existing/proposed annual debt service are reconciled; seasonal needs are considered; base-case coverage is plausible but downside headroom is limited. |
| 5 | Reconciled historical and current evidence supports durable cash generation after all debt service and working-capital swings, with documented downside resilience and credible liquidity headroom. |

## `financial_health` — weight 20

**Inspect:** revenue and profit trend; net assets; liquidity; leverage; receivable and inventory quality; related-party balances; and normalization of one-off items.

| Rating | Observable anchor |
| --- | --- |
| 0 | Financial statements are absent, materially unreliable, or demonstrate unresolved severe insolvency or liquidity distress. |
| 1 | Deteriorating results, weak liquidity, excessive leverage, poor-quality receivables or inventory, related-party balances, or one-off items make underlying performance unclear. |
| 3 | Statements show understandable trends and a supportable normalized view; liquidity, leverage, net assets, working-capital quality, and related-party items are explained, with identifiable weaknesses. |
| 5 | Consistent statements and current data show healthy, well-explained trends, sound liquidity and capitalization for context, good-quality working capital, and transparent treatment of related-party and one-off items. |

## `business_viability` — weight 15

**Inspect:** customer concentration; recurring demand; competitive position; management capability; operational dependencies; and forward-looking evidence such as contracted pipeline, renewal data, orders, or market validation.

| Rating | Observable anchor |
| --- | --- |
| 0 | The business lacks a viable demand basis, has a critical unmitigated dependency, or cannot explain how it will continue operating. |
| 1 | Demand, competitive position, management ownership, dependencies, or forward outlook are weak or unsupported; concentration risk is unaddressed. |
| 3 | A credible operating model and management team support continuing demand; concentration and dependency risks are identified with partial mitigation and some forward evidence. |
| 5 | Diversified or well-managed customer relationships, demonstrable recurring demand, defensible positioning, capable management, resilient operations, and strong forward evidence support the outlook. |

## `borrowing_suitability` — weight 15

**Inspect:** itemized use; requested amount; draw timing; term-to-asset-life alignment; complete sources and uses; and feasible alternative funding.

| Rating | Observable anchor |
| --- | --- |
| 0 | The use, amount, timing, or repayment term is unknown, ineligible, or fundamentally mismatched to the transaction. |
| 1 | Use is vague; sources and uses do not reconcile; the amount is unsupported; or term and asset life are poorly aligned without explanation. |
| 3 | Use, amount, timing, sources and uses, and expected term are specific and mostly supported; term alignment and alternatives are considered, with material follow-up remaining. |
| 5 | A fully reconciled, documented transaction links a right-sized amount and draw timing to itemized uses, sensible term-to-asset-life alignment, and a reasoned assessment of alternative funding. |

## `compliance` — weight 15

**Inspect:** taxes; social insurance; repayment history; existing borrowing terms; licenses; and material legal or regulatory matters.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed serious current delinquency, material misrepresentation, unlawful operation, or a critical legal or regulatory barrier is present. |
| 1 | Arrears, breached borrowing terms, missing licenses, material legal or regulatory issues, or material inconsistencies are unresolved. |
| 3 | Taxes, social insurance, repayment and borrowing terms, licenses, and known legal/regulatory matters are documented and explained; limited remediation or follow-up remains. |
| 5 | Current, consistent evidence supports compliance across taxes, social insurance, debt obligations, licenses, and material legal/regulatory matters, with no unresolved material issue. |

## `documentation` — weight 5

**Inspect:** completed financial statements; current trial balance; debt schedule; cash-flow information; recency; consistency; and management's explanation of changes and material assumptions.

| Rating | Observable anchor |
| --- | --- |
| 0 | Essential records are unavailable and management cannot explain material figures or liabilities. |
| 1 | Statements, trial balance, debt schedule, or cash-flow information are materially incomplete, stale, contradictory, or unexplained. |
| 3 | Completed statements and most current records are available and generally reconcile; management explains main variances, with targeted updates needed. |
| 5 | Complete, current, internally consistent statements, trial balance, debt schedule, and cash-flow information reconcile, and management clearly explains trends, variances, and assumptions. |

## Assessment output discipline

For each rating, name the documents, dates, figures, and assumptions supporting it. Use `unknown` when material information is unavailable, rather than inferring a fact from silence. Submit only confirmed or reported concerns through [red-flags.md](red-flags.md); retain inferred and unknown concerns as follow-up questions.
