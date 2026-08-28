# 計算モデル

観測状態は集計するだけで、点数化も重み付けもしない。`risk_signal_count` は `employment_like` の件数であり、該当性の指標ではない。

```text
fee_to_date   = monthly_fee × months_engaged
remaining_fee = monthly_fee × expected_months_remaining
```

advanced の遡及コストは、利用者が置いた前提だけを使う。

```text
cost(scenario) = monthly_fee × retroactive_months × employer_burden_rate
               + estimated_unpaid_overtime
               + Σ other_costs
ratio(scenario) = cost(scenario) ÷ remaining_fee
```

`base` と `downside` は独立に計算する。片方の前提に `unknown` があっても、もう片方は算出できる状態で残す。`unknown` をゼロで埋めない。

是正案は、`factor_ids` のうち `employment_like` と観測された要素だけを充足対象として数える。`independent` や `unknown` の要素を指定しても充足件数には入らず、どの雇用的要素も指していない是正案は `addresses_no_employment_like_factor` として示す。全是正案を合わせても残る要素を `employment_like_factors_uncovered` として報告する。

```json
{
  "analysis_mode": "advanced",
  "currency": "JPY",
  "engagement": {
    "monthly_fee": {"amount": 500000, "currency": "JPY", "evidence": "confirmed"},
    "months_engaged": 18,
    "expected_months_remaining": 12
  },
  "factors": [
    {"id": "f-direction", "factor": "direction_and_control", "observation": "employment_like", "evidence": "reported"},
    {"id": "f-substitutability", "factor": "substitutability", "observation": "unknown", "evidence": "unknown"}
  ],
  "reclassification_cost_assumptions": {
    "base": {
      "employer_burden_rate": {"value": 0.16, "evidence": "estimated"},
      "retroactive_months": 24,
      "estimated_unpaid_overtime": {"amount": 600000, "currency": "JPY", "evidence": "estimated"},
      "other_costs": [{"name": "手続と専門家費用", "amount": {"amount": 200000, "currency": "JPY", "evidence": "estimated"}}]
    },
    "downside": {
      "employer_burden_rate": {"value": 0.16, "evidence": "estimated"},
      "retroactive_months": 36,
      "estimated_unpaid_overtime": {"amount": 1500000, "currency": "JPY", "evidence": "estimated"},
      "other_costs": []
    }
  },
  "mitigations": [
    {
      "id": "m-place",
      "factor_ids": ["f-direction"],
      "change": "作業指示を業務範囲の合意へ置き換える",
      "feasibility": "high",
      "cost": {"amount": 0, "currency": "JPY", "evidence": "confirmed"},
      "business_impact": "細かな作業指示ができなくなる"
    }
  ]
}
```

`factor` は `direction_and_control`、`work_discretion`、`time_and_place_constraint`、`remuneration_character`、`exclusivity`、`substitutability`、`equipment_burden` のいずれかで、1つの要素につき1件だけ置く。`observation` が `unknown` のときは `evidence` も `unknown` にする。`employer_burden_rate` と `retroactive_months` は利用者が置く前提であり、法定の率や期間を表すものではない。
