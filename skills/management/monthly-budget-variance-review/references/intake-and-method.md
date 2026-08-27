# インテークと分析方法

## インテークと範囲

質問より先に、次の資料の有無を確認する。無い資料は「無い」と記録し、推測で埋めない。

| 資料 | 取れる事実 |
| --- | --- |
| 当月の試算表 | 勘定科目別の実績、締め状態（速報値か確定値か） |
| 当期の予算（または見通し） | 比較の基準、科目の粒度、期中の改定履歴 |
| 前月の予実レビュー | 前月に持ち越した未解決の差異、再確認日 |
| 請求・回収明細 | 計上時期と入金時期のずれ、月またぎの請求 |
| 数量と単価のデータ（セグメント別） | 価格・数量・ミックス分解の入力 |
| 会計処理の変更記録 | 計上基準、勘定科目の付け替え、按分ルールの変更 |

**このスキルは帳簿を締めない。** 試算表が速報値なら、結論はすべて暫定である。締め前の数字を確定値として扱うと、翌月に消える差異へ恒久的な対策を当てることになる。

最初に固定するもの: 対象期間（開始日と終了日）、比較基準（`budget` / `forecast` / `prior_year` / `prior_period`）、通貨、締め状態。比較基準を途中で切り替えない。予算と見通しの両方と比べたい場合は、別々のレビューとして実行する。

収集しないもの: 個人別の給与、取引先との個別のやり取りの原文、顧客の連絡先。

## 重要性の決め方

閾値は**分析を見る前に**決める。差異を見てから閾値を動かすと、説明したくない差異を重要でないことにできてしまう。

- 金額基準（`absolute`）と率基準（`relative_percent`）を両方置き、組合せ方（`rule`）を決める。
  - `either`: どちらかを超えたら重要。小さい科目の大きな率変化と、大きな科目の小さな率変化の両方を拾う。既定として扱いやすい。
  - `both`: 両方を超えたら重要。件数を絞りたいときに使うが、大きな科目の実額の大きい差異を落としやすい。
  - `absolute_only` / `relative_only`: 片方だけを使う。理由を書き残す。
- 科目ごとに事情が違う場合は、その行に `materiality_threshold` を置いて上書きできる。上書きした行は出力の `materiality_source` が `line_threshold` になる。
- 予算が0の行は率を計算できない。実績が0でなければ、金額の大小によらず重要として扱う（`materiality_source` が `zero_budget`）。未予算の収益・支出は、それ自体が予算プロセスの問題である。
- 予算または実績が不明な行は、重要性を判定できない。重要でないとみなさず、レビュー全体を `indeterminate` とする。

## 切り分けの順序

この順序は `skills/management/weekly-founder-review/` の異常値の切り分けと同じであり、それを勘定科目の行レベルに当てはめたものである。**前の段階が未解決の間は、後の段階を原因と断定しない。**

| 順序 | 段階 | 勘定科目での確認内容 | 具体例 |
| --- | --- | --- | --- |
| 1 | `data_quality` | 未計上、二重計上、按分の誤り、抽出範囲、部門コードの付け違い | 外注費の請求書が未入力、同じ入金が二重に計上 |
| 2 | `definition_change` | 勘定科目の付け替え、計上基準の変更、按分ルールの変更、予算側の科目定義とのずれ | 前月まで販管費だった費用を原価に振り替えた |
| 3 | `timing` | 締め日、月またぎの請求、検収時期、支払サイクル、前払・未払の計上 | 8月末請求分が9月計上に回った |
| 4 | `mix` | 商品構成、顧客規模、チャネル、地域、契約形態の構成変化 | 単価の高いプランの比率が下がった |
| 5 | `real_change` | 需要、価格受容、継続率、提供能力、競争、原価構造 | 複数の整合した証拠で新規獲得の減少が続いている |

各段階の値:

- `cleared`: 確認し、この段階では説明されないと判断した。
- `explains`: 確認し、この段階が差異を説明すると判断した。
- `unresolved`: 確認したが結論が出ていない。
- `not_checked`: まだ確認していない。

帰属の決まり方:

- 最初に `explains` となった段階が原因として帰属される。ただし**それより前のすべての段階が `cleared` か `explains` である場合に限る**。
- 前の段階が `unresolved` または `not_checked` のまま後の段階が `explains` を主張した場合、帰属は `premature` となり、`triage_violations` に主張した段階と未解決の段階の両方が記録される。これは分析の欠陥であって、差異の性質ではない。
- どの段階も `explains` でない場合は `unresolved`。5段階すべてが `not_checked` の場合は `not_triaged`。
- 重要でない行は切り分けの対象外とし、`not_triaged` として扱う。違反は記録されない。

## 価格数量ミックス分解

重要な売上・原価の差異について、セグメント別の数量と単価から要因を分ける。

- 予算合計 = Σ(予算数量 × 予算単価)、実績合計 = Σ(実績数量 × 実績単価)、差異 = 実績合計 − 予算合計
- 予算加重平均単価 = 予算合計 ÷ Σ予算数量
- 数量効果 = (Σ実績数量 − Σ予算数量) × 予算加重平均単価
- 価格効果 = Σ(実績数量 × (実績単価 − 予算単価))
- ミックス効果 = 差異 − 数量効果 − 価格効果

**ミックスを残差として置くのは、3つの効果が必ず差異と一致するようにするためである。** 独立に定義すると丸め誤差と定義の重複が残り、合計が合わない分を黙って捨てることになる。その代わり、ミックス効果は価格と数量の測定誤差も吸収する。ミックスが大きい場合は、次を先に確認する。

1. セグメントの定義が予算と実績で同じか。
2. 単価の分母（1契約か1ユーザーか1件か）が揃っているか。
3. セグメントが行全体を覆っているか。`segment_coverage_delta`（予算側）と `segment_actual_coverage_delta`（実績側）が0でなければ `partial_coverage` となり、分解は行の一部にしか当たらない。

分解が意味を持たない場合:

- Σ予算数量が0のとき、加重平均単価を定義できない。分解は `reason: "zero_budget_units"` として効果を `null` とする。0にしない。
- 単価を定義できない役務（一括請負、複合契約）は分解の対象にしない。数量を無理に作らない。

## 是正アクション

帰属した段階ごとに、取るべき手当てが異なる。**すべての差異にアクションを当てない。**

| 帰属 | 手当て | 置くもの |
| --- | --- | --- |
| `data_quality` | 修正・再抽出し、比較をやり直す | 修正担当、再集計の期限。この行の差異は結論に使わない |
| `definition_change` | 同一定義に再構成するか、比較不能と明示する | 定義の対応表、予算側を直すか実績側を直すかの判断 |
| `timing` | **アクションではなく再確認日を置く** | 戻ると見込む月、戻らなかった場合に何を疑うか |
| `mix` | セグメント別に分けて再評価する | どのセグメントで何が起きたか、統合値の限界 |
| `real_change` | 是正または方針変更を検討する | 対象、期待効果、先行指標、担当、期限、停止条件 |
| `premature` | 未解決の段階を先に閉じる | 閉じる担当と期限。この行に事業上の対策を当てない |
| `unresolved` / `not_triaged` | 切り分けを進める | 次に集める最小の証拠 |

`real_change` のうち、単月の揺れではなく構造的な変化と判断したものは `structural_candidates` に入れる。出力の `structural_findings` は `skills/management/quarterly-capital-allocation/` へ渡す提案候補であり、このスキルは投資額を決めない。

タイミング差異に恒久的な費用削減を当てない。翌月に戻る差異へ対策を当てると、翌月は過剰な削減として跳ね返る。

## 計算契約

入力は次の形の単一JSONファイルとし、スキル外に置く。金額と数値は `{"amount": …, "evidence": …}` / `{"value": …, "evidence": …}` の形で渡し、`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれかとする。`unknown` のときは値を `null` とし、0を入れない。

```json
{
  "as_of_date": "2026-09-05",
  "currency": "JPY",
  "period": {
    "label": "2026-08",
    "start": "2026-08-01",
    "end": "2026-08-31",
    "close_state": "preliminary"
  },
  "comparison_basis": "budget",
  "materiality_policy": {
    "absolute": {"amount": 100000, "evidence": "reported"},
    "relative_percent": {"value": 10, "evidence": "reported"},
    "rule": "either"
  },
  "lines": [
    {
      "id": "revenue-saas",
      "label": "SaaS売上",
      "statement_section": "revenue",
      "direction_favorable": "higher",
      "budget": {"amount": 3000000, "evidence": "confirmed"},
      "actual": {"amount": 2600000, "evidence": "reported"},
      "triage": {
        "data_quality": "cleared",
        "definition_change": "cleared",
        "timing": "cleared",
        "mix": "cleared",
        "real_change": "explains"
      },
      "explanation": "新規獲得の減少が継続",
      "explanation_evidence": "reported"
    }
  ],
  "volume_price_lines": [
    {
      "id": "revenue-saas",
      "segments": [
        {
          "id": "smb",
          "budget_units": {"value": 100, "evidence": "confirmed"},
          "actual_units": {"value": 90, "evidence": "confirmed"},
          "budget_unit_price": {"amount": 10000, "evidence": "confirmed"},
          "actual_unit_price": {"amount": 9500, "evidence": "reported"}
        }
      ]
    }
  ],
  "structural_candidates": ["revenue-saas"]
}
```

列挙値: `statement_section` は `revenue | cogs | opex | other`、`direction_favorable` は `higher | lower`、`close_state` は `preliminary | final`、`comparison_basis` は `budget | forecast | prior_year | prior_period`、`materiality_policy.rule` は `either | both | absolute_only | relative_only`、`triage` の各段階は `cleared | explains | unresolved | not_checked`。

`materiality_policy` を省く場合は、すべての行に `materiality_threshold` を置く必要がある。どちらも無い行があれば拒否される。`volume_price_lines` と `structural_candidates` は任意で、いずれも `lines` に存在する `id` を参照しなければならない。

主な出力: 行ごとの `variance` / `variance_percent` / `favorable` / `material` / `materiality_source` / `attribution` / `blocking_stage` / `decomposition`、`triage_violations`、`totals`（区分別合計、粗利、`net_profit_variance`、説明済み・未説明の重要差異額）、`structural_findings`、`review_status`、`missing_inputs`。

`net_profit_variance` は利益への影響として計算する（売上の差異はそのまま、原価・販管費・その他の差異は符号を反転して合算する）。区分の異なる差異をそのまま足し合わせた数値ではない。

`review_status` の優先順位: `indeterminate`（金額不明の行がある、または重要性の値が不明） > `unexplained`（未説明の重要差異額が説明済み額を上回る） > `partially_explained`（未説明の重要差異が残る） > `explained`。締め状態が `preliminary` のときは、どの状態でも `provisional` が `true` となる。

## 報告書形式

次の見出しで日本語の報告書を書く。金額には必ず対象期間、比較基準、証拠状態を添える。

### 意思決定サマリー

当月の利益への影響、説明できた差異と説明できていない差異の額、次月に持ち越す確認事項を3行以内で示す。速報値の場合は暫定である旨を最初に書く。

### 前提と範囲

対象期間、比較基準、通貨、締め状態、重要性の閾値と組合せ方、使った資料、`confirmed` 以外の証拠状態で扱った項目。

### 重要な差異と帰属

重要と判定した行ごとに、差異額、増減率（出せない場合は理由）、有利・不利、帰属した段階、根拠と証拠状態。`premature` の行は帰属ではなく分析の欠陥として別に扱う。

### 要因分解

分解した行の価格効果、数量効果、ミックス効果、3つが差異と一致していること。`partial_coverage` の行は、覆っていない金額を明示する。

### 切り分けの欠陥

`triage_violations` の内容。主張した段階と、未解決のまま残っている段階、閉じる担当と期限。

### 是正アクションと再確認日

帰属ごとの手当て。タイミング差異は再確認日として、実変化は対象・期待効果・先行指標・担当・期限・停止条件を添えて示す。

### 四半期へ渡す論点

`structural_findings` の内容と、`skills/management/quarterly-capital-allocation/` で検討すべき論点。ここでは投資額を決めない。

### 不明点と次に集める根拠

`missing_inputs` に挙がった項目、それが結論のどこを変えうるか、誰にどの資料を求めるか、確定値が出る日。
