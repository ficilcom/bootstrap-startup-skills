# インテークと義務

## 交付決定後に確定する事実

交付決定通知が出た時点で、公募要領の段階では未確定だった多くの事項が確定する。次の資料を質問より先に確認する。

| 資料 | 取れる事実 |
| --- | --- |
| 交付決定通知書 | 交付決定日、交付決定額、補助対象経費の総額、事業実施期間 |
| 交付要綱・交付規程 | 経費区分の定義、対象外経費、補助率、上限、変更承認が必要な事象、財産処分制限 |
| 実績報告の手引き | 必要な証憑の種類、様式、提出期限、検査の観点 |
| 経費区分表・積算内訳 | 区分ごとの承認額。**発注はこの内訳に紐づく** |
| 発注書・契約書・見積書 | 発注日（交付決定日との前後関係）、金額、相見積の件数 |
| 支払記録 | 支払日、支払方法、振込の事実を証明できるか |

**当日再確認するリスト**（交付要綱と実績報告の手引きは改定される。前年度版で進めない）:

1. 経費区分の定義と、区分間の流用が認められる範囲。
2. 相見積の要否と必要件数。金額の閾値で変わることが多い。
3. 支払方法の制限。現金払い、代表者個人名義のカード、相殺、手形が認められるか。
4. 証憑の種類と保存期間。事業終了後も保存義務が続く。
5. 変更承認が必要な事象（金額、内容、実施期間、実施場所、外注先の変更）。
6. 財産処分制限の対象と期間。取得した設備の売却・転用・廃棄に承認が要る。
7. 実績報告の提出期限と、その後の確定検査・請求・入金のおおよその流れ。

`requirements_source` に `authority` / `document` / `url` / `checked_on` / `version` を残す。`checked_on` が基準日より後の日付は拒否される。

収集しないもの: 口座番号、認証情報、従業員の個人情報、事務局担当者の個人名。

## 経費区分と証憑の対応

経費区分ごとに、実績報告で求められる証憑は異なる。次は一般的な対応であり、**必ず当該制度の実績報告の手引きで確認する**。

| 区分 | 典型的に必要な証憑 |
| --- | --- |
| `machinery`（機械装置） | 見積書（相見積を含む）、発注書、契約書、納品書、検収書、請求書、振込記録、設置写真 |
| `system`（システム構築） | 見積書、契約書、仕様書、検収書、請求書、振込記録、画面の記録 |
| `outsourcing`（外注） | 見積書、契約書、成果物、検収書、請求書、振込記録 |
| `personnel`（人件費） | 賃金台帳、出勤簿、作業日報、給与の支払記録 |
| `expert_fee`（専門家経費） | 契約書、業務報告、請求書、振込記録 |
| `travel`（旅費） | 旅費規程、出張命令、報告書、領収書、支払記録 |
| `advertising`（広告宣伝） | 見積書、契約書、成果物（掲載実物・画面）、請求書、振込記録 |
| `other` | 制度の定めによる |

証憑の状態は `held`（保有）、`pending`（発注済み・入手待ち）、`missing`（欠落）、`not_applicable`（該当なし）、`unknown`（未確認）で区別する。

**後から補えない証憑がある。** 相見積は発注前にしか取れない。着手前の状態を示す写真は着工後には撮れない。検収の事実は納品時にしか記録できない。これらは `pending` で放置せず、発生前に確認する。

## 返還リスクの型

次の判定は固定であり、深刻度も固定である。**このスキルは判定を並べるだけで、返還の有無を決めない。**

| 判定 | 深刻度 | なぜ問題になるか |
| --- | --- | --- |
| `ordered_before_approval` | high | 交付決定前の発注・着手は、原則として補助対象外になる。事後に承認されることを前提にしない |
| `eligibility_ineligible` | high | 対象外と確認済みの経費が計画に残っている。実績報告で外れ、自己負担になる |
| `payment_after_project_period` | high | 事業実施期間内に支払が完了していない経費は、対象外になるのが通例である |
| `eligibility_unclear` | medium | 対象・対象外が未確認。確定検査で減額されうる |
| `quote_shortfall` | medium | 必要な相見積の件数に達していない。**発注後には取り直せない** |
| `missing_required_evidence` | medium | 必須の証憑が欠落している。再発行できるものとできないものを分ける |
| `quotes_required_unknown` | medium | 必要件数を確認していない。1件や2件を既定として補わない |
| `cash_payment` | low | 現金払いは支払の事実を証明しにくく、認められない制度もある |
| `pending_required_evidence` | low | 必須の証憑が未入手。入手経路と期限を確認する |

返還リスク額（`amount_at_risk`）は、その経費の対象額 × 補助率で計算する。`clawback_exposure` は**経費ごとに最も深刻な判定だけを数え、一つの経費を重複して計上しない**。一つの経費に3つの判定があっても、失う可能性のある補助金額は一つ分である。

深刻度は確率ではない。`high` は「返還される」ではなく「返還につながる典型例に該当する」という意味である。

## 計算契約

入力は次の形の単一JSONファイルとし、スキル外に置く。金額は `{"amount": …, "evidence": …}`、数値は `{"value": …, "evidence": …}` の形で渡す。`unknown` のときは値を `null` とし、0を入れない。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "grant": {
    "label": "ものづくり補助金 第3回",
    "decision_date": "2026-07-01",
    "approved_total_eligible_cost": {"amount": 8000000, "evidence": "official_current"},
    "subsidy_rate": {"value": 0.5, "evidence": "official_current"},
    "subsidy_cap": {"amount": 4000000, "evidence": "official_current"},
    "project_start_date": "2026-07-01",
    "project_end_date": "2027-02-28",
    "report_due_date": "2027-03-31",
    "expected_payment_date": {"date": "2027-06-30", "evidence": "estimated"},
    "interim_payment_available": false,
    "requirements_source": {
      "authority": "中小企業庁",
      "document": "交付要綱",
      "url": "https://example.go.jp/",
      "checked_on": "2026-08-22",
      "version": "2026年度版"
    }
  },
  "cost_items": [
    {
      "id": "machine-a",
      "label": "加工機",
      "category": "machinery",
      "approved_amount": {"amount": 3000000, "evidence": "official_current"},
      "committed_amount": {"amount": 3200000, "evidence": "confirmed"},
      "planned_payment_date": "2026-11-30",
      "eligibility_status": "confirmed",
      "ordered_before_approval": false,
      "quotes_required": {"value": 2, "evidence": "official_current"},
      "quotes_obtained": {"value": 2, "evidence": "reported"},
      "paid_by": "bank_transfer",
      "evidence_items": [{"kind": "quote", "necessity": "required", "status": "held"}]
    }
  ],
  "cash": {
    "available_cash": {"amount": 3000000, "evidence": "confirmed"},
    "minimum_cash_buffer": {"amount": 1000000, "evidence": "reported"},
    "monthly_net_cash_before_grant": [
      {"month": "2026-08", "amount": {"amount": 200000, "evidence": "reported"}}
    ]
  },
  "financing_options": [
    {
      "id": "tsunagi",
      "label": "つなぎ融資",
      "available_amount": {"amount": 3000000, "evidence": "reported"},
      "lead_time_days": {"value": 30, "evidence": "reported"},
      "status": "reported"
    }
  ]
}
```

列挙値: `category` は `machinery | outsourcing | personnel | travel | advertising | expert_fee | system | other`、`eligibility_status` は `confirmed | likely | unclear | ineligible | not_applicable`、`paid_by` は `bank_transfer | credit_card | cash | other | unknown`、`evidence_items[].kind` は `quote | order | contract | invoice | delivery | bank_transfer_record | photo | timesheet | acceptance`、`necessity` は `required | conditional | optional`、証憑の `status` は `held | pending | missing | not_applicable | unknown`。

`cash.monthly_net_cash_before_grant` は基準日の月から、**最後の支払予定月と入金予定月のうち遅い方まで**を連続して並べる。補助金の入出金は含めない。入金日が `unknown` のときは、最後の支払予定月までを並べる。

### 補助金額の3本立て

補助金額は3つ別々に出し、**平均も合算もしない**。いずれも `min(上限額, 対象額 × 補助率)` で計算する。

| 出力 | 対象に含める経費 | 意味 |
| --- | --- | --- |
| `subsidy_confirmed_only` | `confirmed` のみ | 最も保守的。これだけは入る見込みが立つ額 |
| `subsidy_confirmed_plus_likely` | `confirmed` + `likely` | 未確認の経費が対象外とされた場合の額 |
| `subsidy_including_unclear` | `confirmed` + `likely` + `unclear` | 未確認の経費がすべて認められた場合の額。最も楽観的 |

`ineligible` と `not_applicable` はどの額にも含めない。`cap_binding` は、それぞれの額で上限が拘束したかを示す。

各経費の対象額は `min(発注額, 承認額)` とし、承認額を超えた分は `self_funded_overage`（自己負担）として別に集計する。**超過分が後から承認されると仮定しない。**

### 拒否される入力

補助率が (0, 1] の外、上限額が負、経費の承認額合計が `approved_total_eligible_cost` を超える、事業終了日が開始日より前、実績報告期限が事業終了日より前、中間払いが無いのに入金予定日が事業終了日より前、`ordered_before_approval` が偽なのに支払予定日が交付決定日より前、月次系列の長さや連続性の違反、`id` の重複、列挙値の誤り、証拠状態と値の不整合。

### 拒否せず判定として出すもの

支払予定日が事業実施期間を過ぎている（`high` の判定として表面化させるのが目的であり、入力エラーではない）、発注額が承認額を超えている（自己負担として集計）、発注額が `unknown`（当該経費を全ての補助金額から除外し、`indeterminate` とする）、必要な相見積の件数が `unknown`（`medium` の判定とし、既定値で補わない）。
