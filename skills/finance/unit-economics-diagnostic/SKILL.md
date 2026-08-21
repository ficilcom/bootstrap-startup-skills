---
name: unit-economics-diagnostic
description: Diagnose whether each sale or customer creates contribution profit, calculate gross margin, CAC payback, defensible LTV, break-even volume, and sensitivity for recurring, transactional, or service-project businesses. Use when evaluating unit profitability or whether growth economics support scaling; do not use for statutory accounting, valuation, market sizing, or cash-runway forecasting.
license: MIT
metadata:
  author: ficilcom
---

# ユニットエコノミクス診断

一つの経済単位が生む粗利と限界利益、顧客獲得費の回収、根拠のあるLTV、固定費を賄う販売量、結論を変える感度を診断する。対象は継続課金、取引、サービス案件のいずれか一つであり、法定会計、企業価値評価、市場規模、資金繰り予測ではない。

## 進め方

1. 最初に [インテーク](references/intake.md) を読み、提出済みの財務、販売、広告、顧客、コホート、商品、稼働資料を質問より先に確認する。根拠を `confirmed`、`reported`、`estimated`、`unknown` に区別し、`unknown` をゼロにしない。
2. [モデル選択](references/model-selection.md) を読み、1回の分析につき一つのモード、経済単位、期間、通貨、収益基準、収益ストリームを定義する。異質なストリームは別々に分析する。
3. 少なくとも `base` を作る。価格、原価、獲得費、継続率、数量の不確実性が判断を変え得る場合は `downside` を追加し、`upside` は意思決定に必要な場合だけ加える。
4. [計算モデル](references/calculation-model.md) を読み、必要最小限に匿名化したJSONをスキル外へ作る。スキルのルートで `python3 scripts/calculate_unit_economics.py <input.json>` を実行する。
5. 検証エラーは入力を訂正する。欠損値を推測して完全なダッシュボードを作らない。計算結果を得たら [診断ルール](references/diagnosis-rules.md) を読み、フラグを根拠、制約、利用者の目標へ結び付ける。
6. 結論を変え得る変数だけ感度ケースにし、各ケースを元シナリオから独立して再計算する。別ケースの変更を積み重ねない。
7. [報告書形式](references/report-format.md) を読み、利用者の言語で所定の順番の報告書を作る。粗利、限界利益、固定費負担、獲得費を混同せず、LTV方式と期間を数値の隣に示す。

## 判断上の制約

- 売上ではなく限界利益でCAC回収とLTVを評価する。獲得費プールは分析用の別表示であり、固定費に含まれる同じ費用を利益式で二重控除しない。
- `paid`、`blended`、`fully_loaded`、`marginal` CACを混ぜない。意思決定基準を一つ選び、分子の範囲、顧客コホート、期間整合を明示する。
- 継続率一定モデルは `recurring` かつ正の同期間解約率にだけ使う。解約率ゼロから無限LTVを作らない。
- LTV:CACや回収期間に普遍的な合格値を置かない。利用者が示した方針目標がある場合だけ比較する。
- `profitable_to_scale` は明示された仮定の下で単位採算が拡大を支持するという限定的な判定であり、需要、資金需要、実行力、企業価値を保証しない。
- 数学上の損益分岐点が、提供能力、在庫、稼働時間などのキャパを超える場合は実行可能と扱わない。

## 最新情報と権限

この診断は運営上の管理分析であり、監査済み粗利、税務・法務・会計上の専門判断ではない。分類や制度上の取扱いが結論を左右する場合だけ、当日の権威ある一次情報または適切な専門家へ確認する。

価格、広告、予算、採用・人員、顧客条件、契約、外部連絡、申請、送金、取引を変更または実行する直前に、利用者の明示的な承認を得る。このスキルの利用承認は外部行為の承認ではない。
