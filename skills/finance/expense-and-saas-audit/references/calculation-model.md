# 計算モデルとJSON契約

計算は単一通貨で行う。継続費用は請求周期を年換算し、一時費用には解約料、金銭換算した移行・再設定・教育、失われる割引を含める。税、為替、将来の従量課金、会計上の費用認識は入力に明示されない限りモデル化しない。

```text
current_annual_cost = current_billing.amount × current cycle_multiplier
proposed_annual_cost = proposed_billing.amount × proposed cycle_multiplier
monthly_recurring_savings = (current_annual_cost - proposed_annual_cost) / 12
annual_recurring_savings = current_annual_cost - proposed_annual_cost
one_time_cost = termination_fee + migration + reconfiguration + training
                + lost_discount + (migration_hours + reconfiguration_hours + training_hours)
                  × internal_hourly_cost
first_year_net_savings = annual_recurring_savings - one_time_cost
analysis_period_net_savings = annual_recurring_savings × eligible_days / 365.2425
                              - one_time_cost
```

`eligible_days` は、基準日から `analysis_months` 後の前日までの期間と、有効日以後の重なり日数である。分析期間の継続削減は日割りの推定であり、請求日・前払い・返金・税の実際の現金時期ではない。初年度は有効日からの連続12か月を仮定する。

## 入力

すべての金額は `{"amount": 1200, "evidence": "confirmed"}`、数値は `{"value": 12, "evidence": "reported"}` の形にする。`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれかで、`unknown` の値は必ず `null` にする。既知の金額・数値は0以上の有限数にする。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "analysis_months": 12,
  "expenses": [
    {
      "id": "design-tool",
      "label": "Design tool",
      "category": "saas",
      "billing_cycle": "monthly",
      "proposed_billing_cycle": "monthly",
      "current_billing": {"amount": 30000, "evidence": "confirmed"},
      "proposed_billing": {"amount": 12000, "evidence": "estimated"},
      "action": "rightsize_seats",
      "effective_date": "2026-09-01",
      "classification_signals": ["oversized"],
      "dependency_flags": [],
      "usage": {
        "purchased_seats": {"value": 20, "evidence": "confirmed"},
        "active_seats": {"value": 8, "evidence": "confirmed"},
        "unit_price": {"amount": 1500, "evidence": "confirmed"}
      },
      "contracts": {
        "renewal_date": null,
        "cancellation_notice_days": null,
        "minimum_commitment_end_date": null
      },
      "implementation_costs": {
        "termination_fee": {"amount": 0, "evidence": "confirmed"},
        "migration": {"amount": 0, "evidence": "confirmed"},
        "reconfiguration": {"amount": 0, "evidence": "confirmed"},
        "training": {"amount": 0, "evidence": "confirmed"},
        "lost_discount": {"amount": 0, "evidence": "confirmed"}
      },
      "implementation_effort": {
        "migration_hours": {"value": 0, "evidence": "confirmed"},
        "reconfiguration_hours": {"value": 2, "evidence": "estimated"},
        "training_hours": {"value": 0, "evidence": "confirmed"},
        "internal_hourly_cost": {"amount": 5000, "evidence": "reported"}
      }
    }
  ]
}
```

`category` は `saas`、`infrastructure`、`marketing`、`professional_services`、`contractor`、`facilities`、`insurance`、`other` のいずれか。`billing_cycle` と `proposed_billing_cycle` は現在・提案後の請求周期として `monthly`、`quarterly`、`annual` のいずれか、`action` は `cancel`、`downgrade`、`rightsize_seats`、`annualize`、`renegotiate`、`replace`、`consolidate` のいずれかにする。`annualize` では月次の現在額と年次の提案額を別周期で入力する。

各費目に `usage`、`contracts`、`implementation_costs`、`implementation_effort` を必ず入れる。該当しない既知の費用・工数はゼロ、未確認なら `unknown` を使う。日付の不明は `null` にする。契約固定の候補では更新日と通知期限、最低契約終了日を確認する。

## 判定

スクリプトは外部変更を行わない。`safe_to_execute` は、保護対象依存・連携依存・未確認の金額/実装費/有効日・未確認の契約固定がなく、継続削減が正の候補だけである。`validate_first` は、欠損または契約・連携・席数の検証が必要な候補である。保護対象依存がある、または継続削減が正でない候補は `do_not_cut` とする。これは実行許可ではない。

```bash
python3 scripts/calculate_expense_audit.py <input.json>
```

標準入力なら `<input.json>` に `-` を使う。成功時はJSONを標準出力へ、検証エラーは `error:` を標準エラーへ出し終了コード2を返す。
