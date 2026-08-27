# 計算モデル

## 年齢表

`outstanding = original_amount - paid_amount`

基準日が期日以前なら `current`、超過日数に応じて `days_1_30`、`days_31_60`、`days_61_90`、`over_90` に分ける。不明金額を既知合計へ混ぜず、完全合計は `indeterminate` とする。

顧客比率は、既知の未回収額に対する既知残高の比率であり、不明残高がある場合は全体集中度ではない。報告時に `complete` と既知合計の範囲を添える。

## 支払約束と資金影響

支払約束は `confirmed`、`reported`、`estimated` を別集計する。短期資金への補填は `confirmed` だけを使う。

```text
cash_before_receipts = available_cash - near_term_obligations
cash_after_confirmed_commitments = cash_before_receipts + confirmed_commitments
buffer_gap = max(minimum_cash_buffer - cash, 0)
```

これは約束日までの全入出金を予測するモデルではない。期間中の他の入出金が重要なら、`cash-runway-planner` と同じ基準日・通貨で別途確認する。

## JSON形状

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "cash_context": {
    "available_cash": {"amount": 300000, "currency": "JPY", "evidence": "confirmed"},
    "minimum_cash_buffer": {"amount": 250000, "currency": "JPY", "evidence": "reported"},
    "near_term_obligations": {"amount": 100000, "currency": "JPY", "evidence": "confirmed"}
  },
  "invoices": [
    {
      "id": "inv-001",
      "customer_id": "customer-a",
      "issued_date": "2026-06-01",
      "due_date": "2026-06-30",
      "original_amount": {"amount": 200000, "currency": "JPY", "evidence": "confirmed"},
      "paid_amount": {"amount": 50000, "currency": "JPY", "evidence": "confirmed"},
      "payment_commitment": {
        "date": "2026-08-25",
        "amount": {"amount": 100000, "currency": "JPY", "evidence": "confirmed"}
      },
      "disputed": false
    }
  ]
}
```

`unknown` の金額は `{"amount": null, "evidence": "unknown"}` とする。通貨は全金額で一致させる。
