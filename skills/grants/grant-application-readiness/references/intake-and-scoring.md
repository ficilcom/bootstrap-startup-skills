# インテークと採点

## 前提とする判断

このスキルは `skills/grants/grant-subsidy-fit/` の下流である。上流で既に済んでいるべき判断:

- 制度を追う価値があるか（`explore` モード）。
- 特定制度の条件適合（`specific` モード）。地域、主体、業種、規模、設立日、対象事業、対象経費、着手前条件、自己資金、補助率・上限、併用制限、過去受給、実施期間、報告・監査義務。
- 締切までの実行可能性と機会費用の大枠。
- 総合判断が `進める` か `追加確認` か `見送る` か。

引き継ぐもの: 総合判断（`decision`）と、ゲート要件ごとのステータス（`confirmed` / `likely` / `unclear` / `ineligible` / `not_applicable`）。

**ここで再評価しないもの**: 上記の適格性条件すべて。同じ条件を二度判定すると、上流の判断と食い違ったときにどちらが正しいか分からなくなる。

止める条件:

- ゲート要件に `ineligible` が一つでもあれば、準備度を評価しない。準備を進めても対象にならない。
- 結果を変えうる `unclear` が残っていれば、準備度は出すが `readiness_status` は判定材料にとどめ、まず `grant-subsidy-fit` に戻して確認を完了させる。
- `decision` が `見送る` の場合、このスキルは `blocked` を返す。判断を覆すのはこのスキルの役割ではない。

## 当日確認する範囲

適格性は上流で確認済みとして、このスキルがその日に確認するのは次の4点だけである。いずれも公募回ごとに変わる。

1. **受付状態と締切**。受付中か、予算残があるか、締切の日付・時刻・タイムゾーン。電子申請システムの受付終了時刻が公募要領の締切と異なる場合がある。
2. **提出方法とアカウント要件**。電子申請か郵送か。必要なアカウント（GビズIDなど）の種別と、その発行に要する日数。アカウントは書類ではなく前提条件であり、リードタイムが最も読みにくい。
3. **加点項目とその配点・証明方法**。何点付くか、何をもって証明するか、事後にどんな義務が生じるか。
4. **必要書類一覧と様式の版数**。前回公募の様式で作った書類は無効になりうる。版数と改定日を記録する。

確認したものは、`program.requirements_source` に `authority` / `document` / `url` / `checked_on` / `version` として残す。`checked_on` が基準日より後の日付は拒否される。

## 構成要素の棚卸し

`sections` は申請書の記載項目であり、**公募要領の審査項目から起こす**。よくある構成をテンプレートとして当てはめない。

- 審査項目に書かれた区分をそのまま `sections` の単位にする。書式上の見出しと審査項目が一致しない場合は、審査項目側を採る。
- `weight` は公募要領に書かれた配点を使う。配点が明記されていない場合は、審査項目の数で均等に置き、その旨を報告書に書く。**エージェントが独自の重み付けを発明しない。**
- `requirement_type` は `required`（必ず書く）、`conditional`（該当する場合のみ）、`optional`（任意）。
- `official_criterion_reference` に、公募要領のどこに対応するかを残す。これが無い項目は、審査で評価されない可能性がある。
- `owner` と `estimated_hours` は、締切までの工数を積むために置く。

## draft_stateとevidence_backing

記載項目は2軸で評価する。**文章の完成度が高いことと、主張に根拠があることは別である。**

`draft_state`（文章の完成度）:

| 値 | 状態 |
| --- | --- |
| `not_started` | 手を付けていない |
| `outline` | 見出しと要点だけがある |
| `draft` | 通しで書けているが未推敲 |
| `reviewed` | 第三者（認定支援機関、専門家、共同創業者）の確認を受けた |
| `final` | 提出できる状態 |

`evidence_backing`（根拠の裏付け）:

| 値 | 係数 | 状態 |
| --- | --- | --- |
| `documented` | 1.0 | 見積、実績データ、契約書、公的資料で裏付けられる |
| `reported` | 0.6 | 社内で把握しているが提出できる形にしていない |
| `estimated` | 0.3 | 推計であり、根拠資料がない |
| `unknown` | 0 | 裏付けの有無を確認していない |

採点:

- 得点 = `weight` × `draft_state` の段階（0〜4）÷ 4。
- **`evidence_backing` が `unknown` の項目は、`draft_state` によらず得点0とする。** `reviewed` または `final` なのに根拠が `unknown` の項目は `unsupported_final_sections` に記録される。磨かれた文章に根拠がない状態は、審査で最も崩れやすい。
- `confidence_percent` は `weight` × 証拠係数の加重平均であり、得点とは別に、どれだけ根拠に裏付けられているかを示す。
- 必須項目の合計 `weight` が0の場合、必須の準備度は算出しない。

## 加点要件

加点は「取れば得」ではない。**達成義務と、未達時の返還・取消条件がセットで付いてくる。**

- `status` は `grant-subsidy-fit` と同じ5値を使う。`confirmed` は要件を満たすことを確認済み、`likely` は満たす見込みだが証明資料が未整備、`unclear` は判断できない、`ineligible` は満たせない、`not_applicable` は当該回に存在しない。
- 点数は**ステータス別のバケットに分けるだけで、バケットをまたいで合算しない**。`claimable_points`（確認済み）、`contingent_points`（見込み）、`unresolved_points`（未確認）、`forgone_points`（取れない）を別々に示す。「期待得点」を作ると採択可能性を示唆してしまう。
- `post_award_obligation` には、達成できなかった場合に何が起きるかを書く（返還、加点取消、次回申請への影響）。`obligation_accepted` が `true` でない加点は、`items_with_unaccepted_obligations` として高い深刻度のギャップになる。
- `requires_certification` が `true` の加点は、`certification_item_id` で `kind: "certification"` の準備項目を指す必要がある。証明できない加点は主張できない。

賃上げ、事業承継、デジタル化などの加点は、いずれも申請後の期間にわたる義務を伴うことが多い。義務の期間と、未達の判定方法を確認してから引き受ける。

## 計算契約

入力は次の形の単一JSONファイルとし、スキル外に置く。数値は `{"value": …, "evidence": …}` の形で渡す。`evidence` は `official_current`、`official_historical`、`reported`、`estimated`、`unknown` のいずれかとし、`unknown` のときは値を `null` とする。

```json
{
  "as_of_date": "2026-08-22",
  "program": {
    "label": "ものづくり補助金",
    "round_label": "第3回",
    "requirements_source": {
      "authority": "中小企業庁",
      "document": "公募要領",
      "url": "https://example.go.jp/",
      "checked_on": "2026-08-22",
      "version": "1.2 / 2026-07-10"
    }
  },
  "fit_assessment": {
    "decision": "進める",
    "gate_requirements": [{"id": "eligible-expenses", "status": "confirmed"}]
  },
  "submission_deadline": {"date": "2026-10-15", "time": "17:00", "evidence": "official_current"},
  "sections": [
    {
      "id": "current-business",
      "label": "現在の事業内容",
      "requirement_type": "required",
      "weight": {"value": 3, "evidence": "official_current"},
      "draft_state": "draft",
      "evidence_backing": "reported",
      "official_criterion_reference": "公募要領 p.12 審査項目(1)",
      "owner": "founder",
      "estimated_hours": {"value": 6, "evidence": "estimated"}
    }
  ],
  "scoring_items": [
    {
      "id": "wage-increase",
      "label": "賃上げ加点",
      "points": {"value": 10, "evidence": "official_current"},
      "status": "likely",
      "requires_certification": true,
      "certification_item_id": "wage-pledge",
      "post_award_obligation": "未達の場合は返還または加点取消の対象",
      "obligation_accepted": null
    }
  ],
  "preparation_items": [
    {
      "id": "tax-certificate",
      "label": "納税証明書",
      "kind": "document",
      "necessity": "required",
      "status": "not_started",
      "issuer": "external_authority",
      "lead_time_days": {"value": 7, "evidence": "reported"},
      "expires_on": "2026-12-01",
      "depends_on": ["gbizid"],
      "estimated_hours": {"value": 1, "evidence": "estimated"}
    }
  ],
  "available_hours_per_week": {"value": 8, "evidence": "reported"}
}
```

列挙値: `requirement_type` と `necessity` は `required | conditional | optional`、`draft_state` は `not_started | outline | draft | reviewed | final`、`evidence_backing` は `documented | reported | estimated | unknown`、`kind` は `document | account | review | certification`、準備項目の `status` は `held | requested | in_progress | not_started | not_applicable | unknown`、`issuer` は `external_authority | external_vendor | expert | internal`、`fit_assessment.decision` は `進める | 追加確認 | 見送る`、要件ステータスは `confirmed | likely | unclear | ineligible | not_applicable`。

`id` は `sections`、`scoring_items`、`preparation_items` を**横断して一意**でなければならない。`depends_on` が曖昧にならないためである。締切が基準日より前の場合は拒否される（締切済みの回は `grant-subsidy-fit` の領分）。
