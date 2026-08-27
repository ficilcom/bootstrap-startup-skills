---
name: customer-retention-review
description: Diagnose customer and recurring-revenue retention using aligned cohorts, GRR, NRR, expansion, contraction, churn reasons, and upcoming renewal exposure. Use when a business needs to reduce churn or prepare renewal actions; do not use to infer causation from small samples or automatically contact customers.
license: MIT
metadata:
  author: ficilcom
---

# 顧客維持・更新レビュー

同じ開始コホートの顧客数と継続売上を追跡し、維持、拡張、縮小、解約を分け、期限が近い更新と次の検証を整理する。全顧客の増減や単月の解約率を混ぜず、維持すべき顧客価値と回収可能な原因へ結び付ける。

## 進め方

1. 最初に [インテークと診断方法](references/intake-and-method.md) を読み、契約、請求、利用、サポート、更新、解約、顧客が述べた理由を確認する。不要な個人情報や会話全文は収集しない。
2. コホート開始・終了、単一通貨、継続売上の定義、顧客単位、成熟条件、対象セグメントを固定する。開始後の新規顧客を分母へ加えない。
3. [計算モデル](references/calculation-model.md) に従い匿名化JSONを作り、スキルのルートで `python3 scripts/calculate_retention.py <input.json>` を実行する。ロゴ継続率、GRR、NRR、拡張、縮小、解約売上、更新露出を確認する。
4. 解約理由と更新シグナルを `customer_stated`、内部推論、未確認に分ける。相関を原因と断定せず、セグメント、契約条件、利用、価値実現、品質、支払、担当変更で反証する。
5. [報告書形式](references/report-format.md) で、期限が近い更新、解約・縮小の再発パターン、製品・提供改善、更新行動、最小検証を示す。顧客ごとの行動に次の相互行為、担当、期限、成功・停止条件を置く。

## 判断上の制約

- GRRは拡張を除き、NRRは拡張を含む。同じ開始売上を分母にし、売上認識、請求、入金を混ぜない。
- 小標本、未成熟コホート、季節性、契約期間差を明記する。期限超過の更新を自動的に解約扱いしない。
- 維持率を上げるために採算の悪い値引きや過剰対応を自動推奨しない。貢献利益、提供能力、顧客適合と合わせる。

## 権限境界

顧客連絡、更新提案、値引き、契約変更、サービス付与、CRM更新を自動実行しない。対象、文面・条件、金額、期限、顧客影響を示し、実行直前に明示承認を得る。
