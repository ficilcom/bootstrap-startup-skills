# 計算モデル

```text
answerable_now  = current_state == "implemented" かつ evidence_artifact ∈ {document, configuration, log, third_party}
coverage_rate   = answerable_now 件数 ÷ カテゴリ内の件数
weeks_available = (submission_deadline − as_of_date) の日数 ÷ 7
required_weeks  = 是正工数合計 ÷ available_hours_per_week
```

是正スケジュールは `must` → `should` → `optional` の順に並べ、同じ水準の中では工数の小さい順とする。累積工数を週数へ換算し、`weeks_available` を超えた最初の設問を期限超過の起点として報告する。

工数が `unknown` の設問は同じ水準の末尾へ置き、その設問以降の累積を算出しない。工数合計は `null` にし、既知分だけを `remediation_hours_known_floor` として下限で示す。ゼロで埋めない。

advanced では代替統制の受入状態を分けて扱う。`accepted_by_customer` が `true` の設問だけを `must_gaps_covered_by_control` に入れ、`false` と `null` はギャップとして残す。

```json
{
  "analysis_mode": "advanced",
  "as_of_date": "2026-08-28",
  "submission_deadline": "2026-10-09",
  "currency": "JPY",
  "available_hours_per_week": {"value": 6, "evidence": "reported"},
  "items": [
    {
      "id": "access-control-review",
      "category": "access",
      "requirement_level": "must",
      "current_state": "partial",
      "evidence_artifact": "none",
      "remediation_hours": {"value": 8, "evidence": "estimated"},
      "remediation_cost": {"amount": 50000, "currency": "JPY", "evidence": "estimated"},
      "owner": "founder"
    },
    {
      "id": "backup-restore-test",
      "category": "backup",
      "requirement_level": "should",
      "current_state": "implemented",
      "evidence_artifact": "log",
      "remediation_hours": {"value": 0, "evidence": "confirmed"}
    }
  ],
  "compensating_controls": [
    {
      "item_id": "access-control-review",
      "description": "権限付与を代表者の承認制に限定する暫定運用",
      "accepted_by_customer": null
    }
  ]
}
```

`requirement_level` は `must`、`should`、`optional`。`current_state` は `implemented`、`partial`、`not_implemented`、`unknown`。`evidence_artifact` は `document`、`configuration`、`log`、`third_party`、`none`、`unknown`。`accepted_by_customer` は `true`、`false`、`null` のいずれかで、`null` は未確認を意味する。`submission_deadline` は `as_of_date` より後にする。
