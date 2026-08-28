---
name: annual-operating-plan
description: Build an annual operating plan by turning monthly revenue, gross margin, fixed cost, and committed outflow assumptions into a twelve-month cash path, testing whether that arithmetic reaches user-supplied revenue, gross-profit, and ending-cash targets, and cascading the result into quarterly checkpoints with explicit revision triggers. Use when setting or revising the annual frame that quarterly allocation and monthly reviews operate inside; do not use it as a weekly cash forecast, an investment ranking, a statutory budget, or a prediction that a target will be achieved.
license: MIT
metadata:
  author: ficilcom
---

# 年次事業計画

12ヶ月の売上、粗利率、固定費、確定支出から現金経路を組み、利用者が置いた年次目標へ算術で届くかと、最低現金バッファを守れるかを別々に示す。四半期チェックポイントと改訂トリガまで落とす。目標の達成可能性を判定するものではなく、資金繰り表でも投資候補の比較でもない。

## 進め方

1. 最初に [インテークと方法](references/intake-and-method.md) を読み、会計年度、通貨、期首現金、最低バッファ、収益ストリーム、固定費、確定支出、年次目標を確認する。
2. 12ヶ月の連番、単一通貨、発生ベースの売上に揃える。事実を `confirmed`、`reported`、`estimated`、`unknown` に分け、未決定の数値をゼロで埋めない。
3. 粗利率はストリームごとに置く。過去実績があるなら同じ形へ並べ、計画が実績から跳ねている分の根拠を確認する。根拠が言えない売上は `estimated` にする。
4. [計算モデル](references/calculation-model.md) に従いスキル外へ匿名化JSONを作り、スキルのルートで `python3 scripts/build_annual_plan.py <input.json>` を実行する。シナリオと四半期チェックポイントを見る場合は `analysis_mode` を `advanced` にする。
5. 目標到達（算術）とバッファ割れ月を別々に確認する。届かない場合は [四半期カスケードと改訂トリガ](references/cascade-and-revision.md) に従い、売上、粗利率、固定費のどれで埋めるのかを分けて置く。
6. [報告書形式](references/report-format.md) で、前提、月次・四半期、シナリオ、チェックポイントと改訂トリガ、不足の埋め方を示す。各チェックポイントに判断者と判断期限を置く。

## 判断上の制約

- 目標へ届く算術が組めたことを達成可能とみなさない。需要、提供能力、実行体制は別のゲートとして扱う。
- 年次目標をそのまま四半期へ4分割しない。季節性と獲得リードタイムを反映した後の値だけを閾値にする。
- 不明月は現金経路を打ち切り、その先を推定値で延長しない。打ち切り位置と、確定させる方法・期限を報告する。
- 週次の資金繰りは `cash-runway-planner`、投資候補の順位付けは `quarterly-capital-allocation`、月次の差異分解は `monthly-budget-variance-review` へ渡し、本スキルで代替しない。

## 権限境界

支出、採用、発注、契約、価格変更、借入、納税手続、社内外への計画共有を自動実行しない。税額、保険料額、会計処理は利用者入力の前提として扱い、判定しない。実行直前に対象、金額、時期、資金影響、取り消し可能性を示して利用者の明示承認を得る。このスキルの利用承認は外部行為の承認ではない。
