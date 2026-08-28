---
name: growth-experiment-review
description: Compare growth, acquisition, activation, conversion, retention, or monetization experiments when a founder must decide what to run, hold, stop, or scale from limited evidence, budget, sample, and execution capacity. Do not use for automatic campaign launch or live budget changes.
license: MIT
metadata:
  author: ficilcom
---

# 成長実験レビュー

成長施策を期待値だけで順位付けせず、仮説、証拠、必要サンプル、能力、成功・停止条件まで分けて判断する。

## 進め方

1. [インテークと方法](references/intake-and-method.md) を読み、実験ID、対象ファネル、基準値、費用、工数、貢献、確率、期間、能力を同じ単位へ揃える。
2. 数値を `confirmed`、`reported`、`estimated`、`unknown` に分類する。不明値をゼロや業界平均で埋めない。
3. coreでは経済性と能力を比較する。実行、停止、拡大の判断が必要ならadvancedにし、必要サンプル、観測指標、成功閾値、停止閾値、損失上限、シナリオを追加する。
4. [計算モデル](references/calculation-model.md) に従ってスキル外へ匿名JSONを作り、`python3 scripts/analyze_growth_experiments.py <input.json>` を実行する。
5. エラーは入力で直す。確率、粗利、CVR、継続率、サンプルを推測で補正しない。
6. [報告書形式](references/report-format.md) に従い、経済順位、実験ゲート、反証、停止条件、次の検証、担当者、再評価日を分けて示す。

## 判断上の制約

- `economic_order` は比較可能な期待経済性だけであり、開始・拡大の承認ではない。
- サンプル不足、能力不足、損失上限到達、重要値不明を平均点や高い期待値で相殺しない。
- 成功確率は入力値であり、観測結果から自動補正しない。
- ブランド、法務、プライバシー、顧客体験、計測品質のゲートは経済計算と別に評価する。

## 権限境界

広告出稿、予算変更、顧客接触、トラッキング変更、価格変更、実験開始・停止を実行する直前に利用者の明示承認を得る。この分析の依頼は外部変更の承認ではない。
