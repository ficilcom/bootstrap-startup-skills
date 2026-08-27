# 計算モデル

```text
capacity_units = available_minutes / work_minutes_per_unit
utilization = completed_units / capacity_units
closing_wip = opening_wip + arrivals - completed
backlog_periods = closing_wip / completed_units
first_pass_yield = (completed_units - rework_units) / completed_units
capacity_shortfall = max(demand_units - capacity_units, 0)
```

ゼロ完了では滞留解消期間と初回合格率を `null` にする。候補順は既知の能力不足、期末仕掛り、待ち時間、利用率を順に比較する記述用であり、原因や投資優先度を確定しない。

```json
{
  "process_name": "customer-onboarding",
  "period_label": "2026-W34",
  "demand_units": {"value": 100, "evidence": "reported"},
  "steps": [
    {
      "name": "implementation",
      "opening_wip_units": {"value": 10, "evidence": "confirmed"},
      "arrived_units": {"value": 90, "evidence": "confirmed"},
      "completed_units": {"value": 70, "evidence": "confirmed"},
      "available_minutes": {"value": 600, "evidence": "confirmed"},
      "work_minutes_per_unit": {"value": 8, "evidence": "reported"},
      "wait_time_hours": {"value": 10, "evidence": "reported"},
      "rework_units": {"value": 7, "evidence": "confirmed"},
      "blocked_units": {"value": 12, "evidence": "confirmed"}
    }
  ]
}
```

不明値は `{"value": null, "evidence": "unknown"}` とし、その工程を候補順位から外す。
