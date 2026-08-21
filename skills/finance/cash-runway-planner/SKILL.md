---
name: cash-runway-planner
description: Build a cash-basis 13-week forecast and 12-month runway estimate, identify buffer or cash shortfalls, compare scenarios, and prioritize dated runway actions for bootstrapped or capital-efficient businesses. Use for cash runway, liquidity planning, downside forecasting, or deciding when and what spending to reduce; do not use for statutory cash-flow statements or personal budgeting.
license: MIT
metadata:
  author: ficilcom
---

# キャッシュ・ランウェイ計画

利用可能な現金について、直近13週間の週次資金繰りと、その後12か月までの月次見通しを作る。最低現金バッファ割れと現金ゼロを分け、シナリオ、判断期限、対策の現金効果を示す。これは現金ベースの運営計画であり、会計上の利益予測、法定キャッシュフロー計算書、支払停止の可否、倒産判断ではない。

## 進め方

1. 最初に [インテーク](references/intake.md) を読み、提出資料を質問より先に確認する。基準日、通貨、総現金、使途制限資金、最低現金バッファ、既知の入出金、継続前提を整理し、`quick` または `detailed` を選ぶ。
2. 重要な入力を `confirmed`、`reported`、`estimated`、`unknown` に区別する。`unknown` をゼロに置き換えない。売上の計上日ではなく、実際の回収日・支払日を使う。
3. 少なくとも `base` を作る。回収時期、売上、または重大支払の不確実性が判断を変え得るときは `downside` も作る。`upside` は利用者の判断に必要なときだけ追加する。
4. [計算モデル](references/calculation-model.md) を読み、必要最小限に匿名化したJSONをスキルのディレクトリ外へ作る。複数通貨は、利用者が換算前提と換算日を示さない限り混在させず、通貨別に分ける。
5. スキルのルートで `python3 scripts/calculate_runway.py <input.json>` を実行する。検証エラーは推測で埋めず、入力を訂正する。コア入力または重要な入出金が `unknown` なら、数値結論を作らず `indeterminate` と不足事項を報告する。
6. `warning` または `critical` がある、削減時期を求められた、または施策比較が必要な場合だけ [対策ラダー](references/action-ladder.md) を読む。金額と有効期間を具体化できた対策だけをJSONへ展開して再計算する。
7. [報告書形式](references/report-format.md) を読み、所定の順番で利用者の言語による報告書を作る。13週表、12か月の結果、圧迫要因、意思決定期限、施策効果、前提・不明点を分けて示す。

## 判断上の制約

- `gross_cash - restricted_cash` を利用可能現金とし、`minimum_cash_buffer` は支出として控除しない。バッファ割れは警戒事象、ゼロ割れは資金不足事象として別に扱う。
- 予測期間内に閾値を割らなければ `more_than_12_months` とし、無限または未検証期間の枯渇日を示さない。
- `quick` は常に暫定とし、月次平均が週次の支払集中を隠すことを明記する。
- 施策は元の対象シナリオから個別に再計算する。複数施策を組み合わせる場合は、その組合せを別の明示的な施策として入力し、単独効果の合計をそのまま組合せ効果にしない。
- 給与、税金、債務、契約上の支払、規制上の義務、安全上必要な支出を「安全に削減・延期できる」と断定しない。

## 最新情報と権限

税務、法務、補助金、融資、規制など現在の制度事実が判断を左右する場合だけ、当日の権威ある一次情報を確認し、確認日と出典を示す。予測そのものを専門家の判断、支払猶予の許可、資金調達可能性の保証として扱わない。

顧客・従業員・取引先・金融機関・専門家・行政への連絡、契約解約、支払時期の変更、送金、申請、取引は、実行直前に利用者の明示的な承認を得る。このスキルを使う承認は、それらの外部行為の承認ではない。
