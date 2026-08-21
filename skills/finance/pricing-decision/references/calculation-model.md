# 計算モデルとJSON契約

スクリプトは単一通貨・期間・収益ストリームの判断期間末ランレートを比較する。期間中の累積キャッシュ実現額ではない。

## 値オブジェクト

金額:

```json
{"amount": 20000, "evidence": "confirmed"}
```

数量・率・倍率:

```json
{"value": 100, "evidence": "reported"}
```

`evidence` は `confirmed`、`reported`、`estimated`、`unknown`。`unknown` は値を `null` にする。既知値は0以上の有限数、率と割合は0から1、顧客数と判断期間は整数にする。任意の金額に通貨を付ける場合はトップレベル通貨と一致させる。

## 入力骨格

```json
{
  "mode": "recurring",
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "analysis_period": "month",
  "evaluation_horizon_periods": {"value": 12, "evidence": "reported"},
  "usage_unit_name": "active seat",
  "objective": {"metric": "contribution_after_fixed_costs"},
  "guardrails": {
    "max_active_customer_loss_rate": {"value": 0.05, "evidence": "reported"},
    "min_contribution_margin": {"value": 0.55, "evidence": "reported"},
    "max_weighted_average_price_increase_rate": {"value": 0.25, "evidence": "reported"},
    "max_manual_review_share": {"value": 0.10, "evidence": "reported"},
    "capacity_units_per_period": {"value": 4000, "evidence": "reported"}
  },
  "current_fixed_costs_per_period": {"amount": 3000000, "evidence": "reported"},
  "plans": [],
  "segments": [],
  "proposals": [],
  "sensitivity_cases": []
}
```

`mode` は `recurring`、`transactional`、`service_project`。期間は `week`、`month`、`quarter`、`year`。目的は `revenue`、`contribution_profit`、`contribution_after_fixed_costs`、`arpa`、`active_customers` から選ぶ。目的を省略した場合は数値比較だけを行い、判定を保留する。

## プラン

### 定額

```json
{
  "name": "current-flat",
  "package_label": "Standard",
  "pricing": {
    "model": "flat",
    "flat_fee": {"amount": 20000, "evidence": "confirmed"}
  }
}
```

### 基本料＋従量

```json
{
  "name": "usage-plan",
  "package_label": "Usage",
  "pricing": {
    "model": "base_plus_usage",
    "base_fee": {"amount": 10000, "evidence": "estimated"},
    "included_usage_units": {"value": 5, "evidence": "estimated"},
    "price_per_excess_unit": {"amount": 2000, "evidence": "estimated"},
    "minimum_fee": {"amount": 10000, "evidence": "estimated"},
    "maximum_fee": {"amount": 30000, "evidence": "estimated"}
  }
}
```

```text
raw_charge = base_fee + max(0, usage - included_usage) × excess_unit_price
charge = optional minimum and maximum bounds applied to raw_charge
```

最低・上限額は省略できる。明示的に `unknown` を渡した上限は「上限なし」ではなく計算不能になる。

### 料率

```json
{
  "name": "percentage-plan",
  "package_label": "Transaction",
  "pricing": {
    "model": "percentage",
    "percentage_rate": {"value": 0.025, "evidence": "estimated"},
    "minimum_fee": {"amount": 5000, "evidence": "estimated"}
  }
}
```

`charge = billable_amount_per_customer_per_period × percentage_rate` に任意の最低・上限を適用する。基礎額は契約上の課金基礎であり、会社売上やGMVと同じとは限らない。

### 個別見積

```json
{
  "name": "quoted-plan",
  "package_label": "Enterprise",
  "pricing": {"model": "quoted"}
}
```

現行プランならセグメントに `current_quoted_charge_per_customer_per_period`、移行先ならassignmentに `quoted_charge_per_customer_per_period` を必ず付ける。

## セグメント

```json
{
  "name": "small-teams",
  "current_plan": "current-flat",
  "current_customers": {"value": 100, "evidence": "confirmed"},
  "baseline_retention_rate": {"value": 0.95, "evidence": "reported"},
  "baseline_new_customers_per_period": {"value": 10, "evidence": "reported"},
  "usage_units_per_customer_per_period": {"value": 8, "evidence": "reported"},
  "billable_amount_per_customer_per_period": {"amount": 0, "evidence": "confirmed"},
  "current_quoted_charge_per_customer_per_period": {"amount": 0, "evidence": "confirmed"},
  "fixed_variable_cost_per_customer_per_period": {"amount": 2000, "evidence": "reported"},
  "variable_cost_per_usage_unit": {"amount": 500, "evidence": "reported"}
}
```

現行基準:

```text
retained_existing = current_customers × baseline_retention_rate
active_customers = retained_existing + baseline_new_customers
cost_per_customer = fixed_variable_cost + usage × cost_per_usage_unit
revenue = active_customers × current_charge
contribution_profit = revenue - active_customers × cost_per_customer
contribution_after_fixed_costs = contribution_profit - current_fixed_costs
```

率を適用した顧客数は期待値なので、出力では端数を許す。

## 価格案

```json
{
  "name": "higher-flat-price",
  "validation_stage": "hypothesis",
  "change_summary": ["Raise flat price"],
  "incremental_fixed_costs_per_period": {"amount": 100000, "evidence": "estimated"},
  "one_time_implementation_costs": {"amount": 600000, "evidence": "estimated"},
  "assignments": [
    {
      "segment": "small-teams",
      "target_plan": "higher-flat",
      "migration_policy": "renewal",
      "migration_share_within_horizon": {"value": 0.80, "evidence": "estimated"},
      "manual_review_share": {"value": 0.10, "evidence": "reported"},
      "retention_rate_after_migration": {"value": 0.90, "evidence": "estimated"},
      "new_customer_multiplier": {"value": 1.10, "evidence": "estimated"},
      "usage_multiplier": {"value": 1, "evidence": "reported"},
      "billable_amount_multiplier": {"value": 1, "evidence": "reported"},
      "variable_cost_multiplier": {"value": 1, "evidence": "reported"},
      "transition_discount_rate": {"value": 0.10, "evidence": "estimated"}
    }
  ]
}
```

全セグメントに重複しないassignmentが一つ必要になる。移行割合と手動確認割合の合計は1以下。`grandfathered` は移行割合0、`manual_review` は正の手動確認割合を必要とする。

```text
migration_cohort = current_customers × migration_share
migrated_retained = migration_cohort × migration_retention
migration_losses = migration_cohort × (1 - migration_retention)
legacy_retained = (current_customers - migration_cohort) × baseline_retention
new_customers = baseline_new_customers × new_customer_multiplier
active_customers = migrated_retained + legacy_retained + new_customers
```

手動確認対象は結論が出るまでlegacy料金の母集団に残し、件数を別表示する。

```text
proposal_usage = baseline_usage × usage_multiplier
target_charge = target plan charge at proposal usage or billable amount
effective_migrated_charge = target_charge × (1 - transition_discount)
revenue
  = legacy_retained × current_charge
  + migrated_retained × effective_migrated_charge
  + new_customers × target_charge
proposal_cost_per_customer
  = (fixed_variable_cost + proposal_usage × cost_per_usage_unit)
  × variable_cost_multiplier
contribution_after_fixed_costs
  = revenue - active_customers × proposal_cost_per_customer
  - current_fixed_costs - incremental_fixed_costs
```

一時導入費は `one_time_implementation_costs` として別表示し、ランレート利益から控除しない。

## 価格負担

既存の移行後継続顧客だけを重みにして、実効移行料金と現行料金の差を計算する。加重平均、加重中央値と次の帯を返す。

- `decrease`
- `unchanged`
- `0_to_10_percent`
- `10_to_25_percent`
- `25_to_50_percent`
- `over_50_percent`

現行料金ゼロでは絶対差を残し、率を `not_meaningful_zero_current_price` として加重率から除外する。新規顧客の料金を既存顧客の値上げ負担へ混ぜない。

## 目的・ガードレール・判定

目的は現行との差を返す。ガードレールは利用者が入力したものだけを `passed`、`violated`、`unassessed` で評価する。

- `max_active_customer_loss_rate`
- `min_contribution_margin`
- `max_weighted_average_price_increase_rate`
- `max_manual_review_share`
- `capacity_units_per_period`

判定順序:

1. 目的・重要反応・指定ガードレールが不明: `hold_for_evidence`
2. 目的が改善しない、または違反あり: `reject_under_assumptions`
3. 改善・全指定ガードレール通過・`validated`: `candidate_for_rollout`
4. 改善・違反なし・未検証またはpilot段階: `pilot_first`

判定は実行許可ではない。ガードレールを省略しても普遍的な閾値を追加しない。

## 感度ケース

```json
{
  "name": "retention-downside",
  "source_proposal": "higher-flat-price",
  "overrides": {
    "assignments.small-teams.retention_rate_after_migration": {
      "value": 0.82,
      "evidence": "estimated"
    }
  }
}
```

許可されるパス:

- `incremental_fixed_costs_per_period`
- `one_time_implementation_costs`
- `assignments.<segment>.migration_share_within_horizon`
- `assignments.<segment>.manual_review_share`
- `assignments.<segment>.retention_rate_after_migration`
- `assignments.<segment>.new_customer_multiplier`
- `assignments.<segment>.usage_multiplier`
- `assignments.<segment>.billable_amount_multiplier`
- `assignments.<segment>.variable_cost_multiplier`
- `assignments.<segment>.transition_discount_rate`
- `assignments.<segment>.quoted_charge_per_customer_per_period`

プラン式、移行方針、移行先、目的、ガードレール、検証段階は変更できない。各ケースは元価格案から独立して再計算される。

## 型付き状態と出力

- `indeterminate`: 必要な入力が不明
- `indeterminate_zero_revenue`: 売上ゼロで利益率を算出不能
- `indeterminate_zero_active_customers`: 顧客ゼロでARPAを算出不能
- `not_meaningful_zero_current_price`: 現行価格ゼロで値上げ率に意味がない
- `not_meaningful_zero_current_customers`: 現行顧客ゼロで顧客減少率等に意味がない
- `unassessed`: 指定ガードレールを評価できない
- `objective_not_selected`: 主目的未選択

主な出力は `current`、`proposals`、`sensitivity_cases`。価格案にはセグメント結果、`metrics`、現行との差 `deltas`、`price_burden`、`objective`、`guardrails`、`decision_status`、`decision_reasons`、`missing_inputs`、`estimate_based` が入る。

## 実行

スキルのルートで実行する。

```bash
python3 scripts/calculate_pricing_decision.py <input.json>
```

標準入力は `<input.json>` を `-` にする。成功時はコンパクトJSON、入力・ファイル・JSONエラーは標準エラーへ `error:` と出して終了コード2を返す。検証エラー後の部分的な数値出力を使わない。
