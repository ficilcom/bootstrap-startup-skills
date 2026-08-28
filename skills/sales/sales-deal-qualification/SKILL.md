---
name: sales-deal-qualification
description: Qualify individual B2B sales opportunities when a founder must decide which deals to continue, hold, exit, or personally unblock from incomplete need, budget, authority, timing, champion, process, and commercial evidence. Do not use to auto-update CRM or contact customers.
license: MIT
metadata:
  author: ficilcom
---

# 商談適格性レビュー

案件金額や営業担当者の確信だけでなく、必須条件、証拠、期限、次アクション、阻害要因から商談を継続・保留・撤退・創業者介入へ分ける。

## 進め方

1. [インテークと方法](references/intake-and-method.md) を読み、基準日、予測終了日、通貨、匿名案件ID、顧客ID、金額、確率、期限、次アクションを揃える。
2. 要件を `must` と `should`、結果を `verified`、`reported`、`unknown`、`failed` に分ける。未確認を中立点にしない。
3. coreでは資格ゲートと時期を確認する。意思決定プロセス、相互行動計画、商条件まで確認する場合はadvancedを使う。
4. [計算モデル](references/calculation-model.md) に従い匿名JSONをスキル外へ作り、`python3 scripts/qualify_sales_deals.py <input.json>` を実行する。
5. エラーは入力で訂正する。案件確率、予算、決裁者、期限を自動補正しない。
6. [報告書形式](references/report-format.md) に従い、加重金額順位、資格ゲート、時期、反証、検証対象、停止条件を分ける。

## 判断上の制約

- mustの失敗を総合点、高い金額、確率で救済しない。未確認mustは `conditional` とする。
- `weighted_order` は入力確率による金額比較であり、案件の真の受注確率や優先順位を保証しない。
- 高額かつ阻害要因のある案件だけを創業者介入候補にし、介入目的と打ち切り条件を定める。
- 顧客集中、値引き、法務、セキュリティ、実装能力は別ゲートとして残す。

## 権限境界

CRM更新、顧客連絡、提案、値引き、契約条件提示、失注処理、創業者の予定変更を実行する直前に利用者の明示承認を得る。
