# カレンダーと報告書

## 計算契約

入力は次の形の単一JSONファイルとし、スキル外に置く。金額は `{"amount": …, "evidence": …}` の形で渡し、`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれかとする。`unknown` のときは金額を `null` とし、0を入れない。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "horizon_months": 12,
  "opening_available_cash": {"amount": 5200000, "evidence": "confirmed"},
  "minimum_cash_buffer": {"amount": 1500000, "evidence": "reported"},
  "baseline_net_cash_by_month": [
    {"month": "2026-08", "amount": {"amount": -200000, "evidence": "reported"}}
  ],
  "profile": {
    "fiscal_year_end_month": 3,
    "consumption_tax_status": "taxable",
    "consumption_tax_method": "simplified",
    "consumption_tax_interim": "annual",
    "corporate_tax_interim": "one",
    "has_employees": true,
    "employee_count": {"value": 4, "evidence": "confirmed"},
    "pays_withholdable_compensation": true,
    "social_insurance_enrolled": true,
    "labour_insurance_enrolled": true,
    "withholding_special_exception": "semiannual",
    "resident_tax_special_collection": "monthly"
  },
  "obligations": [
    {
      "id": "consumption-interim-1",
      "label": "消費税 中間納付 第1回",
      "category": "consumption_tax",
      "payment_status": "scheduled",
      "due_date": "2026-11-30",
      "planned_payment_date": null,
      "amount": {"amount": 480000, "evidence": "estimated"},
      "recurrence": "interim",
      "deferrable": "requires_application",
      "source": {
        "authority": "国税庁",
        "document": "消費税の中間申告",
        "url": "https://www.nta.go.jp/",
        "checked_on": "2026-08-22",
        "version": "記載なし"
      }
    }
  ]
}
```

列挙値: `category` は `consumption_tax | corporate_tax | local_corporate_taxes | withholding_income_tax | resident_tax_special_collection | social_insurance | labour_insurance | other_statutory`、`payment_status` は `scheduled | overdue_unpaid | paid`、`recurrence` は `one_time | monthly | interim | annual`、`deferrable` は `no | requires_application | unknown`。

`baseline_net_cash_by_month` は基準日の月から `horizon_months` 分を連続して並べ、法定納付を含めない通常の営業キャッシュを入れる。納付を二重に含めない。

`payment_status` の使い分け:

- `scheduled`: これから納付する。`due_date` は基準日以降でなければならない。`planned_payment_date` は入れない。
- `overdue_unpaid`: 納期限を過ぎて未納。`planned_payment_date`（基準日以降）が必須で、資金繰り上はその日で計上する。`due_date` は過去でよい。
- `paid`: 納付済み。資金繰りから除外し、`excluded_paid` に記録する。

### 月次バケットと残高

- 基準日の月から `horizon_months` 分の暦月を作る。先頭の月は基準日から月末までの部分月として扱う。
- 各納付は、`scheduled` なら `due_date`、`overdue_unpaid` なら `planned_payment_date` の属する月に置く。口座振替で引落日が納期限と異なる場合は、実際に資金が動く日を使う。
- 見通しの範囲外の納付は `outside_horizon` に出す。黙って落とさない。
- 残高: `当月末残高 = 前月末残高 + 通常の営業キャッシュ − 当月の法定納付`。
- `maximum_funding_gap` = `max(0, 最低現金バッファ − 期間中の最低残高)`。判定できた月だけを対象とする。

### 想定納付区分の照合

`coverage` はプロフィールから機械的に導いた想定と、実際に渡された納付区分を突き合わせるだけである。

- `missing_categories`: 想定しているのに、見通し期間内に一件も渡されていない区分。「納付が無い」ではなく「確認できていない」と読む。
- `unexpected_categories`: プロフィール上は想定しない区分の納付が渡された。プロフィールの誤りか、区分の取り違えを疑う。
- `complete` が `true` でも、各区分の中で回数や金額が揃っている保証はない。

## 不確定の扱い

このスキルの中心的な規則は、不確定を後ろの月へ伝播させることである。

- 金額が `unknown` の納付を含む最初の月、または通常の営業キャッシュが `unknown` の最初の月から、その月を含めて以降のすべての月で `determinate` を `false` とし、月末残高を `null` とする。
- `breach_determinable_through` は、残高を信頼できる最後の月を示す。この月より後について「バッファは割れない」と書かない。
- `first_buffer_breach` は、不確定が始まる月より厳密に前で発生した場合にのみ報告する。それ以外は `null` とし、判定できない旨を示す。
- 期首の手元資金が `unknown` のときは、すべての月末残高が `null` となる。月ごとの納付合計は依然として出力されるので、納付の山の把握には使える。
- 最低現金バッファが `unknown` のときは、`first_buffer_breach`、`maximum_funding_gap`、各月の `below_buffer` がすべて `null` となる。月次合計と残高は出力される。
- 各月の `unknown_obligation_count` は、その月に金額不明の納付がいくつあるかを示す。合計額が小さく見えても、この数が0でなければ結論に使わない。

## cash-runway-plannerへの接続

出力の `runway_planner_movements` は、`skills/finance/cash-runway-planner/` の `scenarios[].periods[].movements` と同じ形（`id`、`label`、`direction`、`amount`）に、貼り付け先を示す `target_month` を添えたものである。

接続の手順:

1. `target_month` に対応する月次の period を選び、その `movements` に `id` / `label` / `direction` / `amount` を移す。`target_month` 自体は移さない。
2. `id` は衝突を避けるため `tax-` を前置してある。ランウェイ側で既に同じ納付を計上していないか確認する。**二重計上の排除がこの接続の最大の注意点である。** ランウェイ側の入力に「税金・社会保険」といったまとめ行がある場合は、それを削るか、この出力を使わないかのどちらかにする。
3. `runway_planner_unmodeled` に出た納付は移さない。金額不明のものはランウェイ側でも不明として扱い、0にしない。納付済みのものは既に資金が動いている。見通し範囲外のものは、ランウェイの期間が長い場合のみ手動で追加する。
4. 週次の 13 週予測に載せる場合は、月次の合計ではなく納付日単位で置く。納期限が週の後半に寄ると、週次では見え方が変わる。

金額が `estimated` の納付は、ランウェイ側でも `estimated` のまま渡す。確定額と混ぜない。

## バッファ割れへの対応順序

バッファ割れが出た場合、次の順序で手段を検討する。**未納、納付の先送り、無断の分割はこの一覧に含まれない。** 延滞税・延滞金が生じ、換価の猶予や納税の猶予の要件からも外れうるためである。

1. **入金を早める。** 売掛金の回収（`skills/finance/accounts-receivable-control/`）、前受け・着手金の設定、請求サイクルの前倒し。納付日より前に確実に入る資金を積み上げる。
2. **支出を後ろに動かす、または減らす。** 発注や更新の時期の調整、削減可能な固定費（`skills/finance/expense-and-saas-audit/`）。ただし契約上の支払義務を一方的に遅らせない。
3. **手元資金を厚くする。** 既存の借入枠、当座貸越、追加借入の余地（`skills/finance/debt-service-capacity/` で返済可能性を確認する）。手当てにはリードタイムがあるため、割れる月から逆算して着手日を決める。
4. **制度上の猶予・分割を、正式な手続として検討する。** 納税の猶予、換価の猶予、社会保険料の納付猶予は、いずれも**要件と申請手続があり、事前の申請が必要**である。適用されれば延滞税の一部が軽減される場合があるが、可否は所管が判断する。要件と手続を所管の一次情報で確認し、必要なら税理士・社会保険労務士に相談する。申請しないまま納期限を過ぎることと、猶予を受けることは全く別である。
5. **納付そのものの前提を再確認する。** 中間納付は、前期実績によらない方法での申告が認められる場合がある。適用可否は制度の定めによるため、所管または税理士に確認する。推測で減額しない。

いずれの手段も、割れる月ではなく、その手段のリードタイム分だけ前に着手する必要がある。報告書には着手期限を書く。

## 報告書形式

次の見出しで日本語の報告書を書く。金額には必ず証拠状態を、期日には必ず出典と確認日を添える。

### 意思決定サマリー

納付が集中する月、バッファを割る月と不足額、いつまでに何を手当てする必要があるかを3行以内で示す。判定できない月がある場合は、どこまで判定できたかを明記する。

### 前提と資料

基準日、通貨、見通し月数、決算期、課税事業者区分、納期の特例の適用、使った資料、`confirmed` 以外の証拠状態で扱った納付。

### 納付カレンダー

月ごとの法定納付の合計と区分別の内訳、納付の山の上位、月末残高、バッファ割れの有無。判定できない月は空欄ではなく「判定不能」と書き、理由を添える。

### 想定と実際の突き合わせ

`missing_categories` と `unexpected_categories`、それぞれについて次に確認する資料と所管。

### 期限超過と範囲外

`overdue_obligations` の内容と支払予定日、`outside_horizon` に出た納付とその期日。

### 資金の手当て

必要額の最大値、割れる月、手段ごとのリードタイムと着手期限。未納・遅延を手段として挙げない。

### 不明点と次に確認する事項

`missing_inputs` と `indeterminate_obligations` に挙がった項目、それが結論のどこを変えうるか、誰にどの一次情報を確認するか、確認の期限。
