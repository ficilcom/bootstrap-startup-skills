# 計算モデル

```text
logo_retention = active_starting_customers / starting_customers
GRR = Σ min(end_revenue, start_revenue) / Σ start_revenue
NRR = Σ end_revenue / Σ start_revenue
expansion = Σ max(end - start, 0)
contraction = Σ max(start - end, 0) for active customers
churned_revenue = Σ start_revenue for churned customers
```

開始売上がゼロならGRR・NRRを `null` にする。重要売上が不明なら財務維持率を `indeterminate` とし、既知顧客だけの率を全体値にしない。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "cohort": {"start_date": "2026-05-01", "end_date": "2026-07-31"},
  "renewal_horizon_days": 90,
  "customers": [
    {
      "id": "customer-a",
      "segment": "startup",
      "start_recurring_revenue": {"amount": 100000, "currency": "JPY", "evidence": "confirmed"},
      "end_recurring_revenue": {"amount": 120000, "currency": "JPY", "evidence": "confirmed"},
      "status": "active"
    }
  ],
  "renewals": [
    {
      "customer_id": "customer-a",
      "renewal_date": "2026-09-21",
      "recurring_revenue": {"amount": 120000, "currency": "JPY", "evidence": "confirmed"},
      "risk_signals": ["usage_decline", "no_next_step"],
      "risk_evidence": "reported"
    }
  ]
}
```

解約顧客は終了売上をゼロにし、理由と理由の根拠を別フィールドで記録する。
