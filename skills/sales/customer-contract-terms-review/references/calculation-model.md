# 計算モデル

月は30日として換算する。請求から入金までの月数と、契約開始から初回入金までの日数を次で求める。

```text
receipt_month_offset = ceil((acceptance_lag_days + payment_terms_days) ÷ 30)
receipt_month(e)     = billing_schedule[e].month_index + receipt_month_offset
days_to_first_cash   = (最初の請求月 − 1) × 30 + acceptance_lag_days + payment_terms_days
cumulative[m]        = cumulative[m−1] + 入金[m] − 提供コスト[m]
peak_funded_amount   = max(0, −min(cumulative))
```

累積現金が最も低くなる月が立替ピーク月で、その絶対値が契約完了までに自社が持ち出す最大額になる。累積が一度も負にならない契約は立替ピークをゼロとし、ピーク月を置かない。

いずれかの構成要素が `unknown` の月は累積を打ち切り、`cash_path_truncated_at_month_<m>` を警告に出す。打ち切り前の立替ピークは下限として使える状態で残る。

advanced は次を計算する。

```text
cap_to_contract_value_ratio = 責任上限額 ÷ 契約額
cap_to_annual_revenue_ratio = 責任上限額 ÷ 年商
earliest_termination_month  = min(1 + ceil(termination_notice_days ÷ 30), 期間月数)
unrecovered_cost            = max(0, −cumulative[earliest_termination_month])
committed_months            = 期間月数 + (自動更新なら更新期間月数)
```

責任上限が `uncapped` のときは比率を出さず、利用者が上限比率を定めていれば必ず抵触として扱う。`unknown` は抵触にせず、結果を変える不明点として記録する。両者を同一視しない。

交渉優先順位は金額として測れる条項だけを並べる。無制限の責任は金額が定まらないため先頭へ置き、残りは露出額の降順とする。知財、再委託、自動更新は金額へ換算せず、条項フラグとして別に出す。

```json
{
  "analysis_mode": "advanced",
  "as_of_date": "2026-08-28",
  "currency": "JPY",
  "annual_revenue": {"amount": 30000000, "currency": "JPY", "evidence": "reported"},
  "contract": {
    "value": {"amount": 6000000, "currency": "JPY", "evidence": "confirmed"},
    "duration_months": 6,
    "billing_schedule": [
      {"month_index": 1, "amount": {"amount": 2000000, "currency": "JPY", "evidence": "confirmed"}},
      {"month_index": 4, "amount": {"amount": 2000000, "currency": "JPY", "evidence": "confirmed"}},
      {"month_index": 6, "amount": {"amount": 2000000, "currency": "JPY", "evidence": "confirmed"}}
    ],
    "payment_terms_days": {"value": 60, "evidence": "confirmed"},
    "acceptance_lag_days": {"value": 30, "evidence": "estimated"},
    "delivery_cost_by_month": [
      {"amount": 700000, "currency": "JPY", "evidence": "estimated"}
    ]
  },
  "policy_limits": {
    "max_payment_terms_days": {"value": 45, "evidence": "reported"},
    "max_liability_cap_ratio": {"value": 1.0, "evidence": "reported"},
    "max_uncovered_cost": {"amount": 1500000, "currency": "JPY", "evidence": "reported"}
  },
  "terms": {
    "liability_cap": {"type": "capped", "amount": {"amount": 1200000, "currency": "JPY", "evidence": "confirmed"}},
    "termination_notice_days": {"value": 30, "evidence": "confirmed"},
    "auto_renewal": true,
    "renewal_term_months": 12,
    "ip_assignment": "assigned",
    "subcontracting": "prohibited"
  }
}
```

`delivery_cost_by_month` は `duration_months` と同じ件数にする。`month_index` は1から `duration_months` の範囲で重複させない。`liability_cap.amount` は `type` が `capped` のときだけ置く。上限を定めていない項目は `policy_limits` から省き、`policies_not_set` として報告する。請求合計が契約額と一致しない場合は警告になるが、部分請求として意図しているなら報告書へ理由を書く。
