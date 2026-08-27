---
name: expense-and-saas-audit
description: Audit operating expenses and SaaS subscriptions to identify defensible reductions, rightsizing, alternatives, and vendor negotiations with net savings, timing, and execution priority. Use when a business needs to reduce spend without harming revenue, customer delivery, security, compliance, or continuity; do not use to authorize cancellations, payment stops, or contract changes.
license: MIT
metadata:
  author: ficilcom
---

# 支出・SaaS監査

成長、顧客提供、データ保護、法令順守、業務継続を壊さずに削減できる支出を特定し、候補ごとの純削減額、実現時期、検証事項、実行順序を示す。これは運営上の意思決定支援であり、会計監査、契約解釈、支払停止の可否、または外部変更の実行ではない。

## 進め方

1. 最初に [インテークと分類](references/intake-and-classification.md) を読み、提出済みの請求書、契約、利用状況、更新情報、業務依存を質問より先に確認する。金額・利用状況・契約条件・影響評価を `confirmed`、`reported`、`estimated`、`unknown` に分け、`unknown` をゼロにしない。
2. 費目を重複、未使用・低利用、規模不適合、代替可能、再交渉可能、契約固定で分類する。同時に売上、顧客提供、データ・セキュリティ、法務・規制、業務継続、SSO/API/自動化、切替負荷への依存を記録する。金額だけで順位を決めない。
3. [計算モデル](references/calculation-model.md) を読み、単一通貨の匿名化JSONをスキル外に作る。SaaSでは席数、アクティブ利用、単価、請求周期、更新日、解約通知期限、最低契約、移行・再設定・教育工数を入れる。スキルのルートで `python3 scripts/calculate_expense_audit.py <input.json>` を実行する。
4. 出力の `safe_to_execute`、`validate_first`、`do_not_cut` を分ける。`safe_to_execute` でも実施そのものを承認済みとは扱わない。`validate_first` の不足根拠を先に収集し、候補の結論を変える条件だけを再計算する。
5. [報告書形式](references/report-format.md) に従い、分類、純月次・年次・初年度・分析期間の削減額、実現時期、実行順序、影響、未確定事項を示す。候補は自動実行しない。

## 判断上の制約

- 二重契約、休眠席、過剰プラン、年契約化、再交渉、代替、廃止は別の選択肢として扱う。年契約化の割引は、前払いによる資金繰り・柔軟性・失われる割引を隠さない。
- 解約料、移行、再設定、教育、失われる割引、社内工数を一時費用に含める。月次・年次は継続削減額、初年度は一時費用控除後、分析期間は有効日以降に日割りした純額として区別する。
- 売上、顧客提供、データ・セキュリティ、法務・規制、業務継続に依存するものは `do_not_cut` にする。SSO/API/自動化依存、契約期限・通知期限、利用実態、移行費用が未確認のものは `validate_first` にする。
- `unknown` の金額、利用率、契約情報、切替影響を推測で埋めず、集計の不完全性と次に確認する根拠を示す。契約条項の解釈や規制上の可否が結論を左右する場合は、当日の一次情報または適切な専門家へ確認する。

## 権限境界

ベンダーへの連絡、解約、契約・プラン・席数の変更、支払い停止、ツール設定・データ移行・SSO/API/自動化の変更は、実行直前に利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
