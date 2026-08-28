---
name: capacity-and-backlog-plan
description: Reconcile committed work, backlog, qualified demand, due periods, and delivery capacity when a founder must decide whether to accept, defer, outsource, add overtime, or hire without breaking existing commitments. Do not use to change customer dates or procure capacity automatically.
license: MIT
metadata:
  author: ficilcom
---

# 能力・バックログ計画

確定仕事、バックログ、適格見込みを分け、いつ履行能力が不足するかと、介入案が不足を解消するかを確認する。

## 進め方

1. [インテークと方法](references/intake-and-method.md) を読み、期間単位、判断期間、提供時間、外部能力、仕事ID、期限、必要時間、コミット区分を揃える。
2. 能力・需要・貢献を `confirmed`、`reported`、`estimated`、`unknown` に分類する。不明な稼働率や工数をゼロにしない。
3. coreでは履行需要と潜在需要の不足を分ける。残業、外注、採用、再配列の介入案と需要・能力シナリオを比べる場合はadvancedを使う。
4. [計算モデル](references/calculation-model.md) に従いスキル外へJSONを作り、`python3 scripts/analyze_capacity_backlog.py <input.json>` を実行する。
5. エラーは入力で訂正する。見込み案件を100%の契約需要へ変えず、手戻り、休暇、立上り時間を推測で埋めない。
6. [報告書形式](references/report-format.md) に従い、最初の不足期間、危険な仕事、受注ゲート、介入効果、反証、停止条件を示す。

## 判断上の制約

- `committed`、`backlog`、`qualified` を別表示し、潜在需要で既存の履行不足を隠さない。
- 時間当たり貢献順位で、契約、期限、品質、顧客関係、人の安全を上書きしない。
- 介入による追加能力と費用は利用者入力であり、採用の生産性や外注品質を保証しない。
- 能力不足がある場合は、追加受注の前に既存コミットへの影響と停止条件を確認する。

## 権限境界

受注停止、納期変更、残業指示、外注契約、採用開始、顧客連絡、作業再配分を実行する直前に利用者の明示承認を得る。
