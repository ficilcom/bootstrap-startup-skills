# 計算モデル

## 主要式

- 貢献利益 = 売上 - 変動費
- 貢献利益率 = 貢献利益 / 売上
- 提供1時間当たり貢献 = 貢献利益 / 提供工数
- 能力消費率 = 商品の提供工数 / 利用可能な提供工数

ゼロ工数では時間当たり利益を算出しない。不明な売上・変動費・工数がある商品は不確定として、商品順位とポートフォリオ合計から除外する。

## 入力契約

金額は `{"amount": 100000, "currency": "JPY", "evidence": "confirmed"}`、数量は `{"value": 10, "evidence": "reported"}` の形にする。`unknown` の値は `null` とする。戦略適合は0〜5、率は0〜1とする。

自動出力の `economic_order` は提供1時間当たり貢献だけの順序であり、需要、戦略、契約、ブランドを含む推奨順位ではない。

## advanced契約

`analysis_mode: "advanced"` では、各商品に `demand` と `exit_constraints` を置く。需要は適格パイプライン、バックログ、能力不足による失注、更新率を証拠区分付きで渡す。退出制約は契約中件数、履行残売上、移行費、最短終了日を持つ。

`relationships` は `bundle`、`cross_sell`、`cannibalization`、`shared_capacity` のいずれかとし、効果を単品利益へ加算しない。`reported` 以下は未検証フラグを付ける。

シナリオは商品ごとに証拠区分付きの `revenue_factor`、`variable_cost_factor`、`delivery_hours_factor` を置く。シナリオ別の貢献利益、時間当たり貢献、総提供時間、能力不足を返す。倍率は利用者の仮定であり、予測値として扱わない。

`analysis_quality` は、core経済性を計算できなければ `indeterminate`、需要や退出条件に結論を変え得る不明値があれば `partial` とする。
