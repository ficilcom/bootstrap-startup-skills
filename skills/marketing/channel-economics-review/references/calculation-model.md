# 計算モデル

```text
CAC = spend / acquired_customers
horizon_contribution = customers × contribution_per_customer_per_period × Σ retention^period
horizon_net_contribution = horizon_contribution - spend
marginal_CAC = incremental_spend / incremental_customers
```

回収期間は、顧客当たり累積貢献がCACへ達する最初の期間とする。判断期間内に達しなければ `null` とし、永久に回収不能とは断定しない。継続率はチャネル別コホートに整合する値だけを使う。

```json
{
  "currency": "JPY",
  "period_unit": "month",
  "horizon_periods": 6,
  "channels": [
    {
      "name": "paid-search",
      "spend": {"amount": 120000, "currency": "JPY", "evidence": "confirmed"},
      "acquired_customers": {"value": 12, "evidence": "confirmed"},
      "contribution_per_customer_per_period": {"amount": 4000, "currency": "JPY", "evidence": "reported"},
      "retention_rate_per_period": {"value": 0.9, "evidence": "estimated"},
      "capacity_new_customers": {"value": 20, "evidence": "reported"},
      "marginal_case": {
        "incremental_spend": {"amount": 40000, "currency": "JPY", "evidence": "estimated"},
        "incremental_customers": {"value": 2, "evidence": "estimated"}
      }
    }
  ]
}
```

`unknown` は値を `null` にする。経済順序は、完全な入力を持つチャネルの限界純貢献だけを並べる。
