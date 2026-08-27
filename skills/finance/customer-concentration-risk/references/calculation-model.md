# 計算モデルとJSON契約

この計算は単一通貨、同一対象期間、同一収益基準で正規化済みの顧客集合を前提にする。金額はすべて`{"amount": 500000, "evidence": "confirmed"}`の形で、`evidence`は`confirmed`、`reported`、`estimated`、`unknown`のいずれかとする。`unknown`の`amount`は必ず`null`、既知額は有限数にする。

## 集中度

指標ごとに顧客額を`x_i`、合計を`T = Σx_i`とする。

```text
顧客シェア_i = x_i / T
上位N比率 = 上位N社の Σx_i / T
HHI = Σ(顧客シェア_i^2) × 10,000
```

上位Nは1、3、5、10を返す。顧客数がN未満なら存在する全顧客を使う。金額が不明な顧客が一社でもあれば、その指標の比率とHHIは`indeterminate`とし、既知額の部分集合だけを全社集中度としない。合計ゼロでは比率を作らない。顧客別粗利が負なら粗利のシェア・HHIを作らず、損失顧客を含む粗利集中は別途診断する。

## シナリオ影響

解約または縮小では、顧客の当期売上・粗利に`reduction_rate`を掛ける。

```text
revenue_lost = customer_revenue × reduction_rate
gross_profit_lost = customer_gross_profit × reduction_rate
gross_profit_after_event = total_gross_profit - gross_profit_lost
fixed_cost_coverage_after_event = gross_profit_after_event / fixed_costs
```

固定費は顧客別粗利と同一期間でなければならない。支払遅延は売上・粗利の喪失をゼロとして扱い、現金影響だけをモデルに入れる。`cash_impact_now`は基準日時点または明示した短期期間に失う・遅延する利用可能現金、`recurring_monthly_cash_impact`はその後の月次継続影響であり、いずれも収益から自動換算しない。

```text
cash_after_event = opening_available_cash - cash_impact_now
adjusted_monthly_net_cash_flow = baseline_monthly_net_cash_flow
                                 - recurring_monthly_cash_impact
months_to_buffer = (cash_after_event - minimum_cash_buffer)
                   / -adjusted_monthly_net_cash_flow
months_to_zero = cash_after_event / -adjusted_monthly_net_cash_flow
```

月次純現金増減がゼロ以上なら、一定月次モデルの下で枯渇月数は`not_exhausted_under_constant_monthly_model`とする。イベント直後にバッファまたはゼロを下回る場合は0か月とする。式に必要な入力が不明なら、その結果を`indeterminate`として`missing_inputs`を返す。これは月次モデルであり、週次の支払集中、回収回復、資金調達、代替売上を推定しない。

## JSON例

```json
{
  "as_of_date": "2026-08-22",
  "analysis_period": "2026-07",
  "currency": "JPY",
  "revenue_basis": "recognized_net_revenue",
  "customers": [
    {
      "id": "customer-a",
      "revenue": {"amount": 600000, "evidence": "confirmed"},
      "gross_profit": {"amount": 360000, "evidence": "estimated"},
      "cash_collections": {"amount": 500000, "evidence": "confirmed"}
    }
  ],
  "financial_context": {
    "opening_available_cash": {"amount": 3000000, "evidence": "confirmed"},
    "minimum_cash_buffer": {"amount": 1000000, "evidence": "reported"},
    "baseline_monthly_net_cash_flow": {"amount": -200000, "evidence": "estimated"},
    "fixed_costs": {"amount": 700000, "evidence": "reported"}
  },
  "scenarios": [
    {
      "id": "customer-a-churn",
      "customer_id": "customer-a",
      "event": "churn",
      "reduction_rate": 1,
      "cash_impact_now": {"amount": 500000, "evidence": "reported"},
      "recurring_monthly_cash_impact": {"amount": 500000, "evidence": "estimated"}
    }
  ]
}
```

`event`は`churn`、`contraction`、`payment_delay`のいずれか。前二者は0から1の`reduction_rate`を必須とし、`payment_delay`では`reduction_rate`を入れない。シナリオは重複しないIDを付け、既知の顧客IDだけを参照する。契約終期、更新日、通知期間、支払条件、相関要因、パイプラインは計算入力に無理に数値化せず、報告書の根拠として使う。

## 実行

スキルのルートで実行する。

```bash
python3 scripts/calculate_customer_concentration.py <input.json>
```

標準入力を使う場合は`<input.json>`を`-`にする。成功時はJSONを標準出力へ出す。検証エラーは`error:`で標準エラーへ出し、終了コード2を返す。
