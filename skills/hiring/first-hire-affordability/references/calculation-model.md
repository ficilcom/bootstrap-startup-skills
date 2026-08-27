# 計算モデルとJSON契約

この計算は月次・単一通貨・現金ベースである。`month_index: 0` は基準日を含む最初の月次期間、`hire_start_month` は雇用開始月を表す。計画期間内の月別の現金時期が重要なら、`pre_hire_adjustments` で明示する。会計上の利益、未回収売上、未実行の資金調達を現金へ混ぜない。

## 基本式

```text
monthly_salary = annual_salary / 12
monthly_employer_contributions = monthly_salary * employer_contributions_rate
recurring_hire_cost = monthly_salary + employer_contributions + benefits
                      + equipment_software_monthly + management_time_monthly
incremental_hire_cash = recurring_hire_cost + one_time_costs
                        + productivity_ramp_cost - benefit_ramp_cash
closing_cash = opening_cash + pre_hire_inflows - pre_hire_outflows
               + adjustment_inflows - adjustment_outflows - incremental_hire_cash
```

`separation_contingency_one_time` は、退職・解雇の必然的な支払ではなく、利用者が明示した偶発費用の予算である。実際の義務・適用性を計算器が判断しない。`benefit_ramp_monthly` は開始月から順に適用し、最後の値を以後の成熟便益として繰り返す。`productivity_ramp_costs` は列挙月だけ適用し、その後はゼロとする。

## JSON形状

全ての金額は `{"amount": 500000, "evidence": "confirmed"}`、率は `{"value": 0.15, "evidence": "estimated"}` とする。`unknown` ならそれぞれ `amount` または `value` は `null` でなければならない。既知のゼロは明示的にゼロを入れる。金額は0以上、率は0から1まで、通貨は三文字の大文字コードである。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "opening_available_cash": {"amount": 6000000, "evidence": "confirmed"},
  "minimum_cash_buffer": {"amount": 1500000, "evidence": "reported"},
  "planning_horizon_months": 12,
  "scenarios": [
    {
      "name": "base",
      "hire_start_month": 0,
      "pre_hire_monthly_cash": {
        "inflows": {"amount": 1800000, "evidence": "reported"},
        "outflows": {"amount": 1450000, "evidence": "reported"}
      },
      "pre_hire_adjustments": [
        {
          "month_index": 1,
          "inflows": {"amount": 0, "evidence": "confirmed"},
          "outflows": {"amount": 300000, "evidence": "estimated"}
        }
      ],
      "hiring_costs": {
        "annual_salary": {"amount": 4200000, "evidence": "reported"},
        "employer_contributions_rate": {"value": 0.16, "evidence": "estimated"},
        "benefits_monthly": {"amount": 20000, "evidence": "estimated"},
        "recruiting_one_time": {"amount": 300000, "evidence": "reported"},
        "equipment_software_one_time": {"amount": 180000, "evidence": "estimated"},
        "equipment_software_monthly": {"amount": 15000, "evidence": "estimated"},
        "onboarding_one_time": {"amount": 100000, "evidence": "estimated"},
        "management_time_monthly": {"amount": 40000, "evidence": "estimated"},
        "separation_contingency_one_time": {"amount": 0, "evidence": "reported"},
        "productivity_ramp_costs": [
          {"amount": 150000, "evidence": "estimated"},
          {"amount": 75000, "evidence": "estimated"}
        ],
        "benefit_ramp_monthly": [
          {"amount": 0, "evidence": "estimated"},
          {"amount": 180000, "evidence": "estimated"},
          {"amount": 400000, "evidence": "estimated"}
        ]
      }
    }
  ]
}
```

`scenarios` には重複しない `base`、`downside`、`delayed` を必ず一つずつ入れる。`delayed` の `hire_start_month` は0より大きくする。base と downside は通常、現在開始案として0にするが、別の開始案を評価するならその違いを報告する。`pre_hire_adjustments` は省略時に空配列として扱うが、指定する場合の `month_index` は重複させない。

## 出力と解釈

各シナリオは、採用前の期末現金、採用による純増減、採用後の期末現金、最低現金、最初のバッファ割れ・現金不足月、雇用コスト内訳、累積便益の回収月を返す。`maintains_buffer` は計画期間内の月末現金がバッファ以上、`buffer_breach` はゼロ以上だがバッファ未満、`cash_shortfall` は負、`indeterminate` は重要入力不明である。

最短開始月は、base と downside の両方で月末バッファを維持できる開始月を0から探索した最初の月である。これは求職者の確保、通知期間、法的可否を保証しない。`more_than_horizon` は計画期間以後を評価していない。

実行例:

```bash
python3 scripts/calculate_affordability.py input.json
```

標準入力は `-` を使う。成功時はJSONを標準出力へ出し、検証エラーは標準エラーへ `error:` を出して終了コード2を返す。
