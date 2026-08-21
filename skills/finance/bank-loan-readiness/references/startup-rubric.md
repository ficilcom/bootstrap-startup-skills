# Startup loan-readiness rubric

Use this rubric only with `mode: "startup"`. For every criterion, produce a JSON-ready assessment with `rating` (an integer from 0 through 5), `evidence` (`confirmed`, `reported`, `inferred`, or `unknown`), concise evidence, and a rationale. Use ratings 2 and 4 only where the available evidence falls materially between the adjacent anchors. A rating measures application readiness, not a lender decision.

Distinguish documents or independently verifiable records (`confirmed`) from the applicant's direct statements (`reported`), reasoned conclusions (`inferred`), and missing information (`unknown`). Do not promote an assumption to a fact.

If the required evidence is unavailable, set `evidence: "unknown"`; the scorer awards that criterion zero regardless of the placeholder rating. Describe the missing information and a follow-up question, not an adverse business fact. Apply a low-rating anchor only to a confirmed or reported weakness, not to silence, unavailable records, or an unverified assumption.

## `business_plan` — weight 25

**Inspect:** the customer problem; offering; defined target market; customer-acquisition path; supplier, delivery, staffing, or other operating assumptions; and sales logic that can be externally supported (for example, market evidence, quotations, signed demand, or comparable operating data).

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed or reported facts show no coherent business concept or no usable explanation of customers, offering, and revenue generation. |
| 1 | A concept and broad audience are stated, but problem, market, acquisition, operating assumptions, and sales estimates are largely unsupported or conflict. |
| 3 | The customer problem, offering, target, acquisition path, and key operating assumptions are specific; sales logic is plausible and partly supported, with material assumptions identified. |
| 5 | A coherent, internally consistent plan links a validated customer problem to a differentiated offering, defined market, repeatable acquisition path, feasible operating model, and well-supported sales logic. |

## `funding_plan` — weight 20

**Inspect:** itemized startup and working-capital uses; supplier quotes or calculation support; owner-funding amount and provenance; whether total sources equal total uses; and whether borrowing dependence is reasonable for the venture and use.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed or reported facts show that the requested amount, use of funds, and total project cost are absent or fundamentally incoherent. |
| 1 | Uses are broad estimates, funding sources do not reconcile, or owner funding and its provenance are unclear. |
| 3 | Startup and working-capital needs are itemized with some quotes or calculations; sources reconcile to uses; owner funding is explained; borrowing dependence is plausible but has notable assumptions. |
| 5 | A complete, well-supported sources-and-uses schedule reconciles exactly, substantiates material costs, documents owner-funding provenance, and shows borrowing sized appropriately for a credible launch and cash buffer. |

Do not apply a universal minimum owner-funding ratio. Owner funding is one factor; its provenance, amount, timing, project risk, industry, and the remaining funding structure determine its significance.

## `repayment_capacity` — weight 20

**Inspect:** monthly sales; cost and expense basis; owner living costs where relevant; taxes; existing payments; requested payments; a downside case; and cash remaining after obligations.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed or reported cash-flow assumptions show no viable basis for sales, costs, and debt repayment. |
| 1 | A repayment claim depends on unexplained sales, omits material costs, taxes, living costs, or debt payments, or has no downside case. |
| 3 | A monthly forecast explains sales, costs, expenses, taxes, relevant living costs, existing and requested payments; residual cash is positive in the base case, while downside resilience needs work or support. |
| 5 | A reconciled monthly cash-flow model uses supported assumptions, includes all material obligations and taxes, retains a credible buffer after requested payments, and remains workable under a clearly tested downside case. |

## `founder_capability` — weight 15

**Inspect:** relevant industry and management experience; required licenses; execution evidence such as customers, prototypes, supplier arrangements, or operating results; known gaps; and credible mitigation through hiring, advisers, training, or partners.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed or reported facts show that capability, role ownership, or required qualifications are absent or incompatible with the proposed operation. |
| 1 | The founder has limited relevant experience and material execution gaps without a workable mitigation plan. |
| 3 | Relevant experience or transferable management capability is demonstrated; required qualifications and material gaps are identified, with plausible mitigation and some execution evidence. |
| 5 | Strong directly relevant industry and management track record, required licenses, and meaningful execution evidence are complemented by a credible team and specific mitigation for residual gaps. |

## `compliance` — weight 15

**Inspect:** taxes; social insurance; personal or business repayment history only as voluntarily disclosed; required permits; and consistency across declarations and supporting records.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed unlawful operation, serious current delinquency, or material false declaration is present. |
| 1 | A confirmed or reported material compliance issue, permit gap, tax or insurance concern, or voluntarily disclosed repayment matter remains unresolved or inconsistent. |
| 3 | Required permits and relevant tax, insurance, and disclosed repayment matters are addressed; minor gaps or documentation follow-up remains. |
| 5 | Current, consistent records support required permits, tax and social-insurance compliance, and disclosed repayment history, with no material contradiction. |

Do not request credit files or sensitive personal information beyond what the applicant chooses to provide and what is necessary for this readiness assessment.

## `documentation` — weight 5

**Inspect:** availability, recency, internal consistency, and the applicant's ability to explain material assumptions in the plan, forecast, sources-and-uses schedule, quotes, permits, and supporting records.

| Rating | Observable anchor |
| --- | --- |
| 0 | Confirmed or reported facts show that essential records do not exist or are materially unusable, and material assumptions cannot be explained. |
| 1 | Available documents are materially incomplete, stale, contradictory, or not understandable to the applicant. |
| 3 | Core documents are available and reasonably current; most figures reconcile and material assumptions can be explained, with targeted follow-up needed. |
| 5 | Current, complete, internally consistent records substantiate the application, and the applicant can clearly explain all material assumptions and variances. |

## Assessment output discipline

Keep evidence short and traceable, such as “two signed supplier quotations dated May 2026” rather than a conclusion alone. List unknowns separately so they do not masquerade as low ratings or adverse facts. Route confirmed or reported serious concerns through [red-flags.md](red-flags.md); do not submit `unknown` or `inferred` concerns as red flags.
