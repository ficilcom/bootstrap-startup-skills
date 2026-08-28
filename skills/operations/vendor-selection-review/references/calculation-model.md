# 計算モデル

## 主要式

- 内部移行費 = 移行工数 × 内部時間単価
- 期間TCO = 初期費 + 内部移行費 + (月額 + 月次従量費) × 比較月数 + 退出費
- 平均月額 = 期間TCO / 比較月数

比較月数は正の整数。適合・信頼性・ロックインは0〜5で別表示する。ロックイン4以上は高ロックイン、契約月数が比較期間以上なら長期コミットとしてフラグを付ける。

必須費用が不明な候補はTCOを不確定にし、`cost_order` から除外する。順序は費用だけであり選定推奨ではない。

## advanced契約

`analysis_mode: "advanced"` では、候補ごとに次を証拠区分付きで置く。

- `implementation_external_cost`
- `training_hours`
- `monthly_support_cost`
- `renewal_monthly_cost` と `renewal_start_month`
- `data_export_cost`

advanced TCOは、初期費、内部移行費、導入外注費、教育内部費、更新前後の月額、従量費、サポート費、退出費、データ出力費を比較期間内で合算する。シナリオは候補別の月額・従量費を明示的に上書きし、ゼロも有効な値として扱う。

要件は `must` と `should`、候補の証拠は `verified`、`reported`、`unknown`、`failed` とする。`must` の失敗は `disqualified`、失敗はないが未検証があれば `conditional`、全要件を検証できれば `eligible` とする。費用順位はこの状態を上書きしない。

`analysis_quality` は、advanced費用または要件証拠が不明なら `partial`、費用比較自体ができなければ `indeterminate` とする。
