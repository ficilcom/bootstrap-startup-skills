---
name: sales-forecast-confidence
description: Calibrate a sales forecast using historical error, stage ranges, sample quality, pipeline coverage, opportunity timing, ageing, and customer concentration. Use when a founder needs a defensible revenue range and the deals or evidence that could change it; do not use as a revenue guarantee or permission to alter CRM records.
license: MIT
metadata:
  author: ficilcom
---

# 営業予測の信頼度レビュー

単一の受注予測値を約束として扱わず、過去の予測誤差、偏り、ステージ別実績率、標本量、現在案件から基準・下限・上限の範囲を作る。

## 進め方

1. [インテークと校正方法](references/intake-and-method.md)を読み、予測対象、受注の定義、過去予測と実績、現在パイプライン、ステージ変更履歴を確認する。
2. 同じ通貨、期間、受注日基準、金額定義へ揃える。過去時点で利用できた予測だけを使い、結果を知った後のステージで過去予測を作り直さない。
3. 各入力に `confirmed`、`reported`、`estimated`、`unknown` を付ける。案件台帳があり、滞留、後ろ倒し、顧客集中、期間内外を確認する場合は `advanced` を選び、[案件品質](references/opportunity-quality.md)を読む。
4. [計算モデル](references/calculation-model.md)に従い匿名化JSONを作り、スキルのルートで `python3 scripts/calculate_sales_forecast.py <input.json>` を実行する。
5. [報告書形式](references/report-format.md)で予測範囲、誤差、偏り、目標差、集計整合性、期間外・滞留・集中案件、次回校正日を示す。

## 判断上の制約

- ステージ確率は主観ラベルではなく、同じ定義の過去コホートで校正する。標本量と期間を併記する。
- 加重予測を確約値にしない。大口案件、期限超過、複数案件の同一顧客依存、商談日変更を別のリスクとして扱う。
- 滞留や後ろ倒しを理由に受注率を自動補正しない。確率を変える場合は、同じ定義の履歴または利用者が承認したシナリオを根拠にする。
- 不明な案件額や率をゼロ・100%へ置き換えない。予測範囲を変える不明点は担当と確認期限を置く。

## 権限境界

CRMの金額、ステージ、受注予定日、案件所有者、顧客連絡、経営計画を自動変更しない。修正候補を示し、変更対象と根拠について利用者の明示承認を得る。
