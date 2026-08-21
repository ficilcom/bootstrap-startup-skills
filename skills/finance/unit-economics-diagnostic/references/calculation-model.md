# 計算モデルとJSON契約

計算は単一通貨、単一期間単位、単一の経済単位で行う。スクリプトはPython標準ライブラリだけを使い、同じ入力から同じ結果を返す。

## 値オブジェクト

金額は次の形にする。

```json
{"amount": 12000, "evidence": "confirmed"}
```

数量、率、期間は次の形にする。

```json
{"value": 180, "evidence": "reported"}
```

`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれか。`unknown` の値は必ず `null` とし、既知のゼロと区別する。値は0以上の有限数、率は0から1までとする。任意の金額に `currency` を付ける場合はトップレベル通貨と一致させる。

顧客数と期間数は整数である。`unit_is_discrete` が `true` の場合は `volume_units` と `capacity_units` も整数にする。顧客当たり平均数量は端数を許す。

## 入力例

```json
{
  "mode": "recurring",
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "analysis_period": "month",
  "unit_name": "active-customer-month",
  "unit_is_discrete": true,
  "revenue_basis": "net subscription revenue",
  "scenarios": [
    {
      "name": "base",
      "drivers": {
        "price_per_unit": {"amount": 12000, "evidence": "confirmed"},
        "cogs_per_unit": {"amount": 2500, "evidence": "reported"},
        "other_variable_cost_per_unit": {"amount": 1000, "evidence": "estimated"},
        "volume_units": {"value": 180, "evidence": "reported"},
        "fixed_costs": {"amount": 1200000, "evidence": "confirmed"},
        "new_customers": {"value": 30, "evidence": "confirmed"},
        "units_per_customer_per_period": {"value": 1, "evidence": "reported"},
        "capacity_units": {"value": 220, "evidence": "estimated"}
      },
      "acquisition": {
        "decision_cac_basis": "fully_loaded",
        "decision_cac_scope_complete": true,
        "selected_pool_matches_customer_cohort": true,
        "selected_pool_included_in_fixed_costs": true,
        "marginal_new_customers": {"value": 10, "evidence": "estimated"},
        "costs": {
          "paid": {"amount": 240000, "evidence": "confirmed"},
          "blended": {"amount": 420000, "evidence": "reported"},
          "fully_loaded": {"amount": 600000, "evidence": "estimated"},
          "marginal": {"amount": 180000, "evidence": "estimated"}
        }
      },
      "ltv_model": {
        "method": "constant_retention",
        "churn_rate_per_period": {"value": 0.04, "evidence": "estimated"},
        "period_unit": "month"
      },
      "targets": {
        "max_payback_periods": {"value": 8, "evidence": "reported"}
      }
    }
  ],
  "sensitivity_cases": []
}
```

`mode` は `recurring`、`transactional`、`service_project` のいずれか。`analysis_period` とLTVの `period_unit` は `week`、`month`、`quarter`、`year` のいずれかで一致させる。`scenarios` は重複しない名前を持ち、`base` を必ず含める。

`capacity_units`、`units_per_customer_per_period`、`targets` は、その指標に不要なら省略できる。獲得費の各基準は省略できるが、`decision_cac_basis` は `costs` に存在しなければならない。marginal費用がある場合は `marginal_new_customers` が必要になる。

## LTVモデル

### 観測コホート

```json
{
  "method": "observed_cohort",
  "cohort_customers": {"value": 40, "evidence": "confirmed"},
  "contribution_totals_by_period": [
    {"amount": 320000, "evidence": "confirmed"},
    {"amount": 240000, "evidence": "confirmed"}
  ],
  "period_unit": "month"
}
```

`ltv = supplied periodsのコホート限界利益合計 ÷ original cohort customers`。回収期間は顧客当たり累積限界利益が選択CACに達する最初の1始まり期間である。観測内で届かなければ外挿せず `not_observed_within_horizon` とする。

### 固定期間

```json
{
  "method": "fixed_horizon",
  "expected_units_per_customer_within_horizon": {"value": 5, "evidence": "estimated"},
  "horizon_periods": {"value": 12, "evidence": "reported"},
  "period_unit": "month"
}
```

`ltv = contribution_profit_per_unit × expected_units_per_customer_within_horizon`。出力の `ltv_horizon_periods` と一緒に解釈する。

### 継続率一定

```json
{
  "method": "constant_retention",
  "churn_rate_per_period": {"value": 0.04, "evidence": "estimated"},
  "period_unit": "month"
}
```

`recurring` だけで使える。`expected_lifetime_periods = 1 ÷ churn`、`ltv = customer_contribution_per_period ÷ churn`。ゼロ解約率では `zero_churn_requires_fixed_horizon_or_cohort` を返し、無限を返さない。

## 基本式

```text
gross_profit_per_unit = price_per_unit - cogs_per_unit
gross_margin = gross_profit_per_unit / price_per_unit
contribution_profit_per_unit
  = price_per_unit - cogs_per_unit - other_variable_cost_per_unit
contribution_margin = contribution_profit_per_unit / price_per_unit
revenue = price_per_unit × volume_units
contribution_after_fixed_costs
  = contribution_profit_per_unit × volume_units - fixed_costs
customer_contribution_per_period
  = contribution_profit_per_unit × units_per_customer_per_period
payback_periods = selected_cac / customer_contribution_per_period
ltv_to_cac = contribution_ltv / selected_cac
```

非marginal CACは `acquisition cost pool ÷ new_customers`、marginal CACは `marginal cost pool ÷ marginal_new_customers` とする。選択した一つのCACだけを回収期間とLTV:CACへ使う。

限界利益が正なら `break_even_units = fixed_costs ÷ contribution_profit_per_unit`。離散単位は切上げ数量も返し、連続単位は切上げを適用しない。キャパがあれば適用数量と比較する。

## 型付き状態

- `indeterminate`: 必要入力が不明
- `indeterminate_zero_price`: 価格ゼロのため率を算出不能
- `indeterminate_zero_volume`: 現在数量ゼロのため現在数量での必要価格を算出不能
- `indeterminate_zero_new_customers`: 非marginal CACの分母が確認済みゼロ
- `indeterminate_zero_marginal_new_customers`: marginal CACの分母が確認済みゼロ
- `indeterminate_zero_cohort_customers`: 観測LTVの分母が確認済みゼロ
- `no_finite_break_even`: 単位限界利益がゼロ以下
- `not_recoverable`: 正の顧客限界利益がなくCACを回収できない
- `not_observed_within_horizon`: 観測コホート期間内で未回収
- `not_meaningful_zero_cac`: CACゼロのためLTV:CAC比に意味がない
- `zero_churn_requires_fixed_horizon_or_cohort`: ゼロ解約率を無限LTVにしない
- `not_applicable` / `not_applicable_continuous_unit`: 指標の適用外

既知のゼロ分母は入力エラーにせず、上記状態を返す。入力の構造・型・範囲が不正な場合は検証エラーにする。

## 感度ケース

```json
"sensitivity_cases": [
  {
    "name": "price-down-and-cogs-up",
    "source_scenario": "base",
    "overrides": {
      "drivers.price_per_unit": {"amount": 10800, "evidence": "estimated"},
      "drivers.cogs_per_unit": {"amount": 3000, "evidence": "estimated"}
    }
  }
]
```

許可されるパスは次だけであり、各置換値も証拠付きにする。

- `drivers.` 以下の価格、COGS、その他変動費、数量、固定費、新規顧客、顧客当たり数量、キャパ
- `acquisition.costs.paid|blended|fully_loaded|marginal`
- `acquisition.marginal_new_customers`
- 選択中のLTV方式に対応する `ltv_model.churn_rate_per_period`、固定期間の数量・期間、または観測コホート顧客・限界利益配列
- `targets.max_payback_periods`

モード、通貨、単位、LTV方式、期間単位、CAC基準、シナリオ名は変更できない。構造を変える分析は別シナリオにする。各ケースは `source_scenario` から独立再計算される。

## ブレークポイント

入力から計算できる場合だけ次を返す。

```text
minimum_price_for_positive_contribution = cogs + other_variable_cost
minimum_price_for_break_even_at_current_volume
  = cogs + other_variable_cost + fixed_costs / volume
maximum_variable_cost_for_positive_contribution = max(0, price - cogs)
maximum_cac_for_payback_target
  = customer_contribution_per_period × max_payback_periods
maximum_constant_churn_for_ltv_equal_cac
  = customer_contribution_per_period / selected_cac
```

解約率ブレークポイントが1を超える場合は1へ制限し、`maximum_constant_churn_constraint` を `clamped_to_one` とする。

## 実行と主な出力

スキルのルートで実行する。

```bash
python3 scripts/calculate_unit_economics.py <input.json>
```

標準入力は `<input.json>` を `-` にする。成功時はコンパクトJSONを標準出力へ返す。ファイル、JSON、検証エラーは標準エラーへ `error:` で出し、終了コード2を返す。

- `unit_economics`: 単位価格、粗利・率、限界利益・率
- `period_economics`: 数量、売上、期間粗利・限界利益、固定費控除後
- `break_even`: 必要数量、離散単位切上げ、売上、キャパ判定
- `breakpoints`: 価格・変動費・CAC・解約率の意思決定境界
- `cac`: 基準別CAC、選択基準、範囲・コホート整合情報
- `customer_economics`: 顧客限界利益、回収期間、LTV方式・期間、LTV:CAC
- `diagnostic_flags`: 非排他的な診断結果
- `comparison_to_base`: 計算可能な数値差と追加・解除フラグ
- `sensitivity_cases`: 再計算結果、元シナリオとの差、追加・解除フラグ
- `estimate_based` / `missing_inputs`: 推定依存と不明入力
