# 計算モデル

## 主要式

- 復旧超過 = max(0, 想定復旧時間 - 最大許容停止時間)
- 復旧係数 = max(1, 想定復旧時間 / 最大許容停止時間)
- リスク得点 = 重要度 × 停止確率 × 復旧係数 × (1 + 間接を含む影響依存数)

重要度は1〜5、確率は0〜1。依存グラフは存在する識別子だけを参照し、循環を拒否する。確率、許容時間、復旧時間のいずれかが不明、または許容時間がゼロなら定量順位から除外する。

リスク得点は比較用モデルであり、事故確率や損失額の予測ではない。代替未検証と所有者不在は得点に埋めず別フラグにする。

## 分析モード

`analysis_mode` は省略時 `core`。`advanced` では、各依存に証拠区分付きの `recovery_point_objective_hours`、`expected_data_loss_hours`、`minimum_operating_capacity_rate`、`alternative_capacity_rate`、`alternative_recovery_hours` を置く。能力率は0〜1とする。

試験は `last_test_date` と `test_result`（`passed`、`failed`、`not_run`、`unknown`）で表す。`tested_alternative` と矛盾させない。複合障害は `scenarios` に一意な名前と `failed_dependencies` を置く。

- RPO超過 = max(0, 想定データ損失時間 - RPO)
- 代替能力不足 = max(0, 最低稼働能力率 - 代替能力率)

`recovery_layers` は依存先を先に復旧する層であり、同じ層の順序は優先順位ではない。`priority_tier` は確率予測ではなく、重要度、確認済み超過、試験結果、不明値から作る作業順の候補である。

`analysis_quality` は選択モード、証拠件数、結論を変え得る不明点、警告を返す。主要順位を作れなければ `indeterminate`、一部を計算できても重要な不明点が残れば `partial` とする。
