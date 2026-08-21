# 計算モデルとJSON契約

計算は単一通貨の現金ベースで行う。会計上の売上・費用ではなく、予測期間中に実際に受け取る入金と支払う出金を期間へ割り当てる。

## 基本式

```text
opening_available_cash = gross_cash - restricted_cash
closing_available_cash = opening_available_cash + cash_inflows - cash_outflows
maximum_funding_gap = max(0, minimum_cash_buffer - lowest_closing_available_cash)
runway_months = crossing_date までの日数 / 30.4375
```

`minimum_cash_buffer` は支出ではない。期末利用可能現金がバッファを下回った最初の期間と、ゼロを下回った最初の期間を別々に記録する。期間内補間は報告書で推定として補足できるが、スクリプトの基準日は期間末日とする。

## 期間境界

### `detailed`

- `w01` は `as_of_date` から最初の日曜日まで。基準日が月曜日なら7日、日曜日なら1日の部分週になる。
- `w02` から `w13` は月曜日から日曜日までの連続7日間。
- `w13` の翌日からは月次期間とし、最初と最後は部分月を許す。
- 最終期間は `as_of_date` を12か月進めた日の前日で終える。

### `quick`

- `as_of_date` から各暦月末までの連続した月次期間を作る。
- 最初と最後は部分月を許す。
- 最終期間は `as_of_date` を12か月進めた日の前日で終える。

全期間は隙間と重複がなく、前期間の終了日の翌日に始める。既知の入出金は実際に現金が動く期間へ置く。月次平均を部分月へ機械的に日割りする場合は、その方法を `estimated` の仮定として明示する。

## 金額オブジェクト

すべての金額は次の形にする。

```json
{"amount": 500000, "evidence": "confirmed"}
```

`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれか。`unknown` の `amount` は必ず `null` とし、それ以外は0以上の有限数とする。出金は負数ではなく、`direction: "outflow"` と正の金額で表す。

## 入力例

次は構造を示す短縮例であり、実際の `detailed` 入力には13週と12か月終端までの全期間が必要になる。

```json
{
  "mode": "detailed",
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "gross_cash": {"amount": 5000000, "evidence": "confirmed"},
  "restricted_cash": {"amount": 500000, "evidence": "confirmed"},
  "minimum_cash_buffer": {"amount": 1000000, "evidence": "reported"},
  "scenarios": [
    {
      "name": "base",
      "periods": [
        {
          "id": "w01",
          "start_date": "2026-08-22",
          "end_date": "2026-08-23",
          "granularity": "week",
          "movements": [
            {
              "id": "invoice-a",
              "label": "Invoice A collection",
              "direction": "inflow",
              "amount": {"amount": 1200000, "evidence": "reported"}
            },
            {
              "id": "payroll-aug",
              "label": "August payroll",
              "direction": "outflow",
              "amount": {"amount": 900000, "evidence": "confirmed"}
            }
          ]
        }
      ]
    }
  ],
  "modeled_actions": []
}
```

`scenarios` には重複しない名前を付け、`base` を必ず含める。同一シナリオ内の期間IDと入出金IDは重複させない。入出金に `currency` を付ける場合はトップレベル通貨と一致させる。

## 警戒ポリシー

未指定時の運営上の目安は次のとおり。

- `critical`: 最初の閾値割れが13週以内
- `warning`: 13週後から6か月未満
- `watch`: 6か月以降、12か月の予測期間内
- `stable`: 予測期間内にバッファもゼロも割らない
- `indeterminate`: 不明情報により計算できない

これは普遍的な安全基準ではない。利用者の方針を使う場合は、正の整数かつ昇順の日数で次を追加し、報告書に方針を記す。

```json
"warning_policy": {
  "critical_days": 91,
  "warning_days": 183,
  "watch_days": 366
}
```

`watch_days` は基準日から12か月後までの日数以上にする。これにより、カスタム方針も予測期間全体を覆う。

## 対策の展開

スクリプトは反復ルールを推測しない。対策の各現金効果と一時費用を、該当する期間へ展開してから渡す。

```json
"modeled_actions": [
  {
    "id": "reduce-tools",
    "label": "Reduce unused software",
    "scenarios": ["base", "downside"],
    "start_period": "w03",
    "end_period": "m12",
    "recurrence": "expanded_monthly_savings",
    "cash_effects": [
      {"period_id": "w03", "amount": {"amount": 25000, "evidence": "estimated"}},
      {"period_id": "w04", "amount": {"amount": 25000, "evidence": "estimated"}}
    ],
    "implementation_costs": [
      {"period_id": "w03", "amount": {"amount": 10000, "evidence": "reported"}}
    ]
  }
]
```

`cash_effects` は利用可能現金を増やす正の効果、`implementation_costs` は実施に必要な出金である。対象期間は `start_period` と `end_period` の範囲内に置く。各対策は元シナリオから独立して再計算される。組合せを評価する場合は、すべての効果と費用を一つの別対策へ展開する。

## 実行

スキルのルートで実行する。

```bash
python3 scripts/calculate_runway.py <input.json>
```

標準入力を使う場合は `<input.json>` を `-` にする。成功時はJSONを標準出力へ出す。検証エラーは `error:` で標準エラーへ出し、終了コード2を返す。

## 主な出力

- `opening_available_cash`: 利用可能な開始現金
- `provisional`: quickモードまたは不明入力を含むか
- `warning_status`: baseシナリオの警戒区分
- `scenarios[].periods`: 各期間の開始残高、入金、出金、純増減、終了残高
- `buffer_crossing_date` / `zero_crossing_date`: 最初の期間末閾値割れ
- `buffer_runway` / `zero_cash_runway`: 月数または `more_than_12_months`
- `lowest_closing_available_cash`: 予測期間中の最低残高
- `maximum_funding_gap`: バッファ維持に必要な最大追加資金
- `comparison_to_base`: 最低残高、必要資金、閾値日数の差
- `modeled_actions`: 各対策の総効果、一時費用、純効果、再計算結果、差分

`indeterminate` のシナリオは数値期間表を出さず、`missing_inputs` を返す。検証エラー時は部分的な数値結論を使わない。
