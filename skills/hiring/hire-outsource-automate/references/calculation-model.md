# 計算モデルとJSON契約

スクリプトはPython標準ライブラリだけを使う。同一入力から同一出力を返すが、推定を事実に変換したり、候補を自動採択したりはしない。

## 共通の基準

トップレベルの `currency`、`period_unit`、`horizon_periods` が比較基準である。候補ごとに期間や通貨を変えない。`horizon_periods` は、意思決定で意味がある最短の共通期間（例: 12か月）にする。異なる通貨を換算する必要があるときは、利用者が為替レート、基準日、根拠を決めてから入力通貨を一つに統一する。

金額は次の形式で、すべて非負の同一通貨とする。

```json
{"amount": 250000, "evidence": "reported"}
```

工数や期間は次の形式で表す。

```json
{"value": 16, "evidence": "estimated"}
```

`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれかである。`unknown` の `amount` または `value` は必ず `null` にし、既知のゼロと区別する。既知の値は有限の0以上とする。スクリプトは候補の金額入力または定量便益に `unknown` があれば、その候補を `indeterminate` とし、部分的な正味効果や回収期間を返さない。

## 入力形

```json
{
  "currency": "JPY",
  "period_unit": "month",
  "horizon_periods": 12,
  "candidates": [
    {
      "name": "hire-operator",
      "kind": "hire",
      "fit": {
        "workload_hours_per_period": {"value": 120, "evidence": "reported"},
        "workload_variability": "volatile",
        "strategic_importance": "high",
        "confidentiality": "medium",
        "quality_control": "direct",
        "time_to_readiness_periods": {"value": 2, "evidence": "estimated"},
        "reversibility": "low",
        "internal_learning_value": "high",
        "management_overhead_hours_per_period": {"value": 8, "evidence": "estimated"}
      },
      "costs": {
        "one_time": {
          "recruiting": {"amount": 300000, "evidence": "reported"},
          "onboarding": {"amount": 150000, "evidence": "estimated"},
          "equipment": {"amount": 120000, "evidence": "reported"},
          "exit_or_switching": {"amount": 0, "evidence": "estimated"}
        },
        "recurring_per_period": {
          "compensation": {"amount": 500000, "evidence": "reported"},
          "employer_burdens_and_benefits": {"amount": 100000, "evidence": "estimated"},
          "management": {"amount": 40000, "evidence": "estimated"},
          "tools_and_workspace": {"amount": 20000, "evidence": "reported"}
        }
      },
      "benefits_per_ready_period": [
        {"category": "cost_avoidance", "label": "Founder time redeployed", "amount": {"amount": 700000, "evidence": "estimated"}}
      ],
      "pessimistic_case": {
        "benefit_multiplier": {"value": 0.7, "evidence": "estimated"},
        "cost_multiplier": {"value": 1.15, "evidence": "estimated"}
      }
    }
  ]
}
```

`period_unit` は `week`、`month`、`quarter`、`year` のいずれかである。候補名は一意で、`kind` は `hire`、`outsource`、`automate`、`defer_or_stop` のいずれかにする。`fit` の水準は `low`、`medium`、`high`、仕事量の変動性は `steady`、`cyclical`、`volatile`、品質管理は `direct`、`shared`、`limited`、可逆性は `low`、`medium`、`high` とする。これらは点数化しない比較情報である。

## 必須の費用内訳

各 `costs` オブジェクトは候補種別ごとに次のキーをすべて持つ。該当しない既知の費用にはゼロを入れ、未確認なら `unknown` を使う。

| 種別 | `one_time` | `recurring_per_period` |
| --- | --- | --- |
| `hire` | `recruiting`, `onboarding`, `equipment`, `exit_or_switching` | `compensation`, `employer_burdens_and_benefits`, `management`, `tools_and_workspace` |
| `outsource` | `sourcing_and_contracting`, `transition`, `switching_or_exit` | `contract`, `vendor_management`, `internal_quality_review` |
| `automate` | `build`, `integration_and_data_migration`, `rollback_or_replacement` | `software_and_infrastructure`, `maintenance`, `monitoring`, `failure_handling` |
| `defer_or_stop` | `wind_down`, `restart_or_replacement` | `residual_obligations`, `management` |

`benefits_per_ready_period` は空配列でもよいが、その候補の定量便益はゼロとなる。各要素は `incremental_revenue`、`cost_avoidance`、`loss_avoidance` のいずれかの `category`、空でない `label`、証拠付き `amount` を持つ。能力余力、品質、学習、戦略的選択肢の価値を無理に金額化しない。

## 式と出力

`R = horizon_periods - time_to_readiness_periods`（0未満なら0）とする。

```text
one_time_cost = one_time の全項目の合計
recurring_cost_per_period = recurring_per_period の全項目の合計
benefit_per_ready_period = benefits_per_ready_period の全項目の合計
total_cost = one_time_cost + recurring_cost_per_period × horizon_periods
total_quantified_benefit = benefit_per_ready_period × R
net_quantified_effect = total_quantified_benefit - total_cost
```

回収期間は、初期費用を引いた後、各期間の経常費用を引き、立ち上がり完了後の期間だけ便益を足した累積額が初めて0以上になる期末である。期間内に達しない場合は `not_within_horizon`、稼働後の1期間あたり便益が経常費用以下の場合は `not_recoverable_within_horizon` とする。立ち上がりと経常費用は比較期間の最初から発生する保守的な前提であり、実際に後払いなら入力期間または判断メモで調整する。

`pessimistic_case` は任意である。ある場合、`benefit_multiplier` は0から1、`cost_multiplier` は1以上とし、全一時・経常費用と全定量便益へそれぞれ乗じて同じ式で計算する。未入力時は `not_provided` と返す。不明入力による `indeterminate` と、既知の悪化要因を入れた悲観結果は別の出力フィールドである。

主な出力は `candidates[].base_case`、`candidates[].pessimistic_case`、`missing_inputs`、`estimate_based`、`economic_ranking` である。`economic_ranking` は計算可能な候補の正味定量効果順であり、品質・機密性・実行条件を反映した推奨順位ではない。

## 実行

```bash
python3 scripts/compare_options.py <input.json>
```

標準入力を使う場合は `<input.json>` を `-` にする。成功時はJSONを標準出力へ出す。入力、ファイル、JSONのエラーは標準エラーへ `error:` と出し、終了コード2を返す。
