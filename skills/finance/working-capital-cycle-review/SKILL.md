---
name: working-capital-cycle-review
description: Analyze receivables, inventory, payables, customer deposits, DSO, DIO, DPO, cash conversion cycle, and cash-release targets when a founder needs to reduce working-capital pressure. Do not use to change payment terms, collections, inventory orders, bank records, or accounting entries automatically.
license: MIT
metadata:
  author: ficilcom
---

# 運転資本サイクルレビュー

売掛金、在庫、買掛金、前受金の資金拘束を期間と残高基準を揃えて計算し、利用者定義の改善案が解放・消費する現金を示す。

## 進め方

1. [インテークと方法](references/intake-and-method.md) を読み、通貨、測定日数、平均または期末残高、売上、売上原価、各残高の期間と定義を揃える。
2. 数値を `confirmed`、`reported`、`estimated`、`unknown` に分ける。在庫ゼロと在庫不明、前受金ゼロと不明を混同しない。
3. coreではDSO、DIO、DPO、CCC、純運転資本を計算する。利用者定義の目標と残高シナリオから現金影響を見る場合はadvancedを使う。
4. [計算モデル](references/calculation-model.md) に従いスキル外へJSONを作り、`python3 scripts/analyze_working_capital.py <input.json>` を実行する。
5. エラーは入力で訂正する。期間の不一致、売上・原価ゼロ、不明残高を業界平均で埋めない。
6. [報告書形式](references/report-format.md) に従い、サイクル、現金影響、実行可能性、反証、停止条件、担当者を示す。

## 判断上の制約

- 期末残高だけの比率は季節性や月中変動を含まないため、平均残高と同じ確度で扱わない。
- DSO・DIO・DPOの普遍的な正解を置かず、利用者が定義した目標だけを計算する。
- 正の現金解放額は回収可能性や実現時期を保証しない。負値は現金消費として保持する。
- 早期回収割引、欠品、品質、仕入先関係、契約、税務・会計処理を別ゲートにする。

## 最新情報と権限

契約、回収、会計、税務の判断が必要なら当日の一次情報と適切な専門家へ確認する。顧客・仕入先連絡、支払条件変更、回収、発注、支払延期、送金、会計入力を実行する直前に利用者の明示承認を得る。
