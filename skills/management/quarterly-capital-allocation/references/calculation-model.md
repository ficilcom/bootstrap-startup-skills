# 計算モデル

各候補またはポートフォリオについて、初期費用を基準日直後に控除し、月次で次を計算する。

```text
cash[m] = cash[m-1] + baseline_net_cash[m] + benefits[m] - monthly_costs[m] - downside_extra_costs[m]
net_cash_effect = Σ benefits - upfront_cost - Σ monthly_costs - Σ downside_extra_costs
```

基準・悲観のいずれかで月末または初期控除後の現金が最低バッファを下回れば、両ケースでの配分可能とはしない。回収月は候補固有の累積便益が候補費用へ達する最初の月とする。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "quarter_months": 3,
  "opening_cash": {"amount": 500000, "currency": "JPY", "evidence": "confirmed"},
  "minimum_cash_buffer": {"amount": 250000, "currency": "JPY", "evidence": "reported"},
  "baseline_net_cash_by_month": [
    {"amount": 50000, "currency": "JPY", "evidence": "reported"},
    {"amount": 50000, "currency": "JPY", "evidence": "reported"},
    {"amount": 50000, "currency": "JPY", "evidence": "reported"}
  ],
  "proposals": [
    {
      "name": "crm-improvement",
      "strategic_fit": "supports_priority",
      "reversibility": "medium",
      "upfront_cost": {"amount": 100000, "currency": "JPY", "evidence": "confirmed"},
      "monthly_costs": [
        {"amount": 20000, "currency": "JPY", "evidence": "confirmed"},
        {"amount": 20000, "currency": "JPY", "evidence": "confirmed"},
        {"amount": 20000, "currency": "JPY", "evidence": "confirmed"}
      ],
      "base_benefits": [
        {"amount": 0, "currency": "JPY", "evidence": "estimated"},
        {"amount": 80000, "currency": "JPY", "evidence": "estimated"},
        {"amount": 100000, "currency": "JPY", "evidence": "estimated"}
      ],
      "downside_benefits": [
        {"amount": 0, "currency": "JPY", "evidence": "estimated"},
        {"amount": 20000, "currency": "JPY", "evidence": "estimated"},
        {"amount": 40000, "currency": "JPY", "evidence": "estimated"}
      ],
      "downside_extra_costs": [
        {"amount": 0, "currency": "JPY", "evidence": "estimated"},
        {"amount": 10000, "currency": "JPY", "evidence": "estimated"},
        {"amount": 10000, "currency": "JPY", "evidence": "estimated"}
      ],
      "dependencies": ["sales-owner"],
      "benefit_overlap_group": "revenue-operations"
    }
  ],
  "portfolios": [{"name": "crm-only", "proposals": ["crm-improvement"]}]
}
```

4つの月次配列は `quarter_months` と同じ長さにする。基準純現金はマイナスを許容し、費用・便益は非負とする。
