---
name: channel-economics-review
description: Compare acquisition channels using aligned blended and marginal CAC, contribution payback, retention assumptions, capacity constraints, and evidence quality. Use when deciding where a capital-efficient business should add, hold, reduce, or test marketing spend; do not use as attribution proof or authorization to change live campaigns.
license: MIT
metadata:
  author: ficilcom
---

# 集客チャネル経済性レビュー

集客チャネルを、同じ顧客定義・期間・通貨・貢献利益基準で比較し、追加予算が回収できるか、運用能力や測定上の制約があるかを判断する。平均実績だけで増額せず、限界ケースと証拠品質を分ける。

## 進め方

1. 最初に [インテークと比較方法](references/intake-and-method.md) を読み、広告費、制作・代理店費、リード、顧客、売上、変動費、継続、チャネル運用工数を確認する。顧客やキャンペーンは匿名化する。
2. 目的、単一通貨、期間単位、判断期間、獲得顧客の定義、貢献利益の範囲、アトリビューション規則を固定する。チャネル間で異なる場合は比較せず別表にする。
3. `confirmed`、`reported`、`estimated`、`unknown` を入力ごとに付ける。自然流入、ブランド効果、営業支援、重複接触を根拠なく一つのチャネルへ帰属させない。
4. [計算モデル](references/calculation-model.md) に従い匿名化JSONを作り、スキルのルートで `python3 scripts/calculate_channel_economics.py <input.json>` を実行する。平均CACと限界CAC、回収期間、判断期間の純貢献、継続仮定、能力制約を分けて確認する。
5. [報告書形式](references/report-format.md) で、`増額`、`維持`、`縮小`、`最小検証`、`測定修正` の候補を示す。自動出力の順序は定量化済みの限界経済性だけであり、戦略適合・能力・アトリビューションを含む最終順位ではない。

## 判断上の制約

- 平均CACが良くても、次の追加予算の限界CACが悪ければ増額根拠にしない。限界データがなければ小さいテストと停止条件を置く。
- 売上ではなく、同じ範囲の変動費を控除した顧客当たり貢献を使う。回収期間をLTVの代替にせず、継続率は観測コホートか明示的な推定として扱う。
- ゼロ件、小標本、未成熟コホート、計測変更、複数接点を隠さない。件数と期間を添え、単一期間の順位を恒久的優位と断定しない。

## 権限境界

広告予算、入札、キャンペーン、代理店契約、トラッキング、クリエイティブ、顧客連絡を自動変更しない。実行直前に対象、変更額、期間、成功・停止条件、想定影響を示して利用者の明示承認を得る。
