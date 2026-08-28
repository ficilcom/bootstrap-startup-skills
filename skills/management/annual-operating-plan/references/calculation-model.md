# 計算モデル

月 `m` を1から12として次を計算する。

```text
revenue[m]      = Σ stream.monthly_revenue[m]
gross_profit[m] = Σ stream.monthly_revenue[m] × stream.gross_margin_rate
net_cash[m]     = gross_profit[m] − fixed_costs[m] − committed_outflows[m]
ending_cash[m]  = ending_cash[m−1] + net_cash[m]      ending_cash[0] = opening_cash
```

いずれかの構成要素が `unknown` の月は `net_cash[m]` を算出せず、その月以降の現金経路を打ち切って `cash_path_truncated_at_month_<m>` を警告に出す。打ち切り前の月の値、最低現金、バッファ割れ判定は使える状態で残る。

四半期は3ヶ月ずつの4区間とし、売上・粗利・純現金は区間合計、期末現金は区間末月の値を使う。年次の売上と粗利は12ヶ月すべてが既知のときだけ合計する。

目標判定は `planned ≥ target` の算術だけを返し、不足額は `max(0, target − planned)` とする。期末現金目標への不足は、同額の追加粗利が必要という意味であり、達成可能性の判断ではない。

advancedのシナリオは次で置き換える。

```text
scenario_revenue[m]      = revenue[m] × revenue_multiplier
scenario_gross_profit[m] = scenario_revenue[m] × (gross_margin_rate + margin_delta)
scenario_fixed[m]        = fixed_costs[m] × cost_multiplier
```

確定支出はシナリオでも変えない。実効粗利率が負になる入力は許容するが `negative_effective_margin` を警告に出す。

```json
{
  "analysis_mode": "advanced",
  "fiscal_year_start": "2026-04-01",
  "currency": "JPY",
  "opening_cash": {"amount": 6000000, "currency": "JPY", "evidence": "confirmed"},
  "minimum_cash_buffer": {"amount": 3000000, "currency": "JPY", "evidence": "reported"},
  "revenue_streams": [
    {
      "id": "subscription",
      "monthly_revenue": [
        {"amount": 1000000, "currency": "JPY", "evidence": "estimated"}
      ],
      "gross_margin_rate": {"value": 0.6, "evidence": "reported"}
    }
  ],
  "fixed_costs_by_month": [
    {"amount": 500000, "currency": "JPY", "evidence": "reported"}
  ],
  "committed_outflows": [
    {"name": "consumption-tax", "month_index": 3, "amount": {"amount": 1200000, "currency": "JPY", "evidence": "confirmed"}}
  ],
  "annual_targets": {
    "revenue": {"amount": 15000000, "currency": "JPY", "evidence": "reported"},
    "gross_profit": {"amount": 7000000, "currency": "JPY", "evidence": "reported"},
    "ending_cash": {"amount": 8000000, "currency": "JPY", "evidence": "reported"}
  },
  "scenarios": [
    {
      "id": "downside",
      "revenue_multiplier": {"value": 0.8, "evidence": "estimated"},
      "margin_delta": {"value": -0.05, "evidence": "estimated"},
      "cost_multiplier": {"value": 1.1, "evidence": "estimated"}
    }
  ],
  "quarterly_checkpoints": [
    {"quarter": 1, "metric": "revenue", "threshold": {"amount": 3000000, "currency": "JPY", "evidence": "reported"}, "revision_trigger": "下回れば獲得計画を再設計する"}
  ]
}
```

`monthly_revenue` と `fixed_costs_by_month` は12件ちょうどにする。`unknown` の金額は `amount` を `null` にし、ゼロを入れない。`month_index` は1から12、`quarter` は1から4、`metric` は `revenue`、`gross_profit`、`ending_cash` のいずれか。
