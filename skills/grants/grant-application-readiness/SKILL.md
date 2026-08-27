---
name: grant-application-readiness
description: Score how ready a specific grant or subsidy application package is across narrative sections, official scoring criteria, and required documents and accounts, then back-schedule every remaining gap against the submission deadline and the founder's available hours. Use after a program has already been judged worth pursuing and the round is open; do not use it to decide eligibility or program fit, to predict selection, or to submit anything.
license: MIT
metadata:
  author: ficilcom
---

# 補助金申請の準備度評価

特定の補助金・助成金について、申請書の記載項目、公募要領に書かれた加点要件、必要書類とアカウントの準備状況を評価し、残ったギャップを締切から逆算して着手期限に並べる。これは準備度の把握であり、適格性の判定、採択の予測、申請の提出ではない。

## 進め方

1. このスキルは `skills/grants/grant-subsidy-fit/` の `specific` モードで `進める` または `追加確認` に至った評価**から始まる**。[前提とする判断](references/intake-and-scoring.md#前提とする判断) を読み、条件別ステータス（`confirmed` / `likely` / `unclear` / `ineligible` / `not_applicable`）を入力として引き継ぐ。地域、主体、業種、規模、設立日、対象事業、対象経費、着手前条件、併用制限を**再評価しない**。ゲート要件に `ineligible` があるか、結果を変えうる `unclear` が残っていれば、ここで止めて `grant-subsidy-fit` に戻す。
2. [当日確認する範囲](references/intake-and-scoring.md#当日確認する範囲) の4点だけを、その日のうちに一次情報で確認する。受付状態と締切（時刻とタイムゾーン）、提出方法とアカウント要件、加点項目の配点と証明方法、必要書類一覧と様式の版数。公募要領の版が変わっていないかを必ず見る。
3. [構成要素の棚卸し](references/intake-and-scoring.md#構成要素の棚卸し) に従い、公募要領の審査項目から記載項目を起こす。**配点は公募要領に書かれた値だけを使い、書かれていない配点をエージェントが作らない。**
4. 各記載項目に、[draft_stateとevidence_backing](references/intake-and-scoring.md#draft_stateとevidence_backing) の2軸を付ける。文章の完成度と、根拠の裏付けは別に評価する。
5. [加点要件](references/intake-and-scoring.md#加点要件) に従い、各加点項目のステータスと、達成できなかった場合の返還・取消条件を記録する。義務を引き受けられるか確認せずに「取りに行く」と結論づけない。
6. [計算契約](references/intake-and-scoring.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/score_application_readiness.py <input.json>` を実行する。出力は準備度であり、申請の提出も問い合わせも行わない。
7. [期限逆算](references/gaps-and-report.md#期限逆算) で各準備項目の着手期限と余裕日数を確認し、[ギャップの優先順位](references/gaps-and-report.md#ギャップの優先順位) に従って埋める順序を決める。[報告書形式](references/gaps-and-report.md#報告書形式) に従い、準備度、埋めるべきギャップ、着手期限、[不採択でも残る価値](references/gaps-and-report.md#不採択でも残る価値) を示す。

## 判断上の制約

- 適格性の再判定を行わない。ゲート要件に `ineligible` または未解決の `unclear` があれば、この評価を続けず `grant-subsidy-fit` に戻す。
- 準備度スコアは採択確率ではない。審査基準の重み、採択率、審査員の評価を推測せず、公募要領に書かれた配点だけを使う。
- 加点要件を、達成義務を引き受けられるか確認せずに「取りに行く」と結論づけない。返還・取消条件を必ず併記する。引き受けられない義務を伴う加点は、得点ではなく費用である。
- 加点のステータス別の点数を合算しない。「期待得点」を作らない。合算した数値は採択可能性を示唆してしまう。
- 書類のリードタイムを希望的に短縮しない。発行元が外部の場合、実際の所要日数と、余裕日数の根拠を残す。
- 文章の完成度と根拠の裏付けを別に評価する。`final` でも根拠が `unknown` なら得点にしない。磨かれた文章に根拠がない状態は、このスキルが検出すべき失敗そのものである。
- 締切の時刻とタイムゾーン、電子申請システムの受付終了時刻を、日付だけで代用しない。
- 必要書類の有効期限が締切より前に切れる場合、取得済みであっても未取得と同じ扱いにする。

## 権限境界

このスキルは、準備度の評価、ギャップの一覧、着手計画を作るだけである。申請の提出、電子申請システムやアカウントの作成・ログイン、認定支援機関・専門家・事務局への問い合わせ、見積依頼、発注、契約、支出、個人情報の共有を自動実行しない。実行直前に、行為、相手先、共有範囲、費用、法的拘束、取り消し可能性を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
