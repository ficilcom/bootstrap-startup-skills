---
name: tax-and-social-insurance-calendar
description: Map Japanese statutory payment obligations - consumption tax, corporate and local taxes including interim payments, withholding income tax, special-collection resident tax, social insurance, and labour insurance - onto a monthly cash schedule, find the first month an operating cash buffer is breached, and export the obligations as movements for a runway forecast. Use when planning cash around tax and social-insurance due dates or checking whether a filing period is affordable; do not use it to determine tax liability, filing method, rates, or eligibility for deferral, and do not treat its output as a tax determination.
license: MIT
metadata:
  author: ficilcom
---

# 納税・社会保険の資金繰りカレンダー

利用者が確認した納付義務を月次のキャッシュに載せ、納付が集中する月、最低現金バッファを割る月、必要な資金の最大額を示す。これは資金繰りの準備作業であり、税額の計算、申告方法の判定、料率や納期限の決定、猶予・分割の可否の判断ではない。

## 進め方

1. 最初に [インテークと出典](references/intake-and-sources.md) を読み、申告書控え、納付書、口座振替の通知、算定基礎届、年度更新の申告書、給与計算の集計を質問より先に確認する。マイナンバー、口座番号、個人別の給与明細は収集しない。
2. 基準日、通貨、見通し月数、決算期、課税事業者区分、納期の特例の適用状況を一つに固定する。[事業者プロフィール](references/intake-and-sources.md#事業者プロフィール) の各項目が、どの納付区分を想定するかを変える。
3. 税率、料率、納期限、中間申告の要否と回数、納期の特例の可否を、記憶やスクリプトから決めない。[当日確認チェックリスト](references/intake-and-sources.md#当日確認チェックリスト) に従って一次情報で確認し、確認日、様式の版、出典を [出典台帳](references/intake-and-sources.md#情報区分と出典台帳) に残す。
4. 各納付を `confirmed`、`reported`、`estimated`、`unknown` に区別する。確定額と概算額を合算しない。金額が不明な納付を0として扱わない。
5. [計算契約](references/calendar-and-report.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/build_tax_calendar.py <input.json>` を実行する。出力は資金繰りの見通しであり、納付や口座振替の設定を行わない。
6. [不確定の扱い](references/calendar-and-report.md#不確定の扱い) に従い、どの月まで残高を信頼できるかを確認する。不明な納付額より後の月の残高は結論に使わない。全社の資金繰りに組み込む場合は [cash-runway-plannerへの接続](references/calendar-and-report.md#cash-runway-plannerへの接続) に従い、二重計上を排除する。
7. バッファ割れが出た場合は [バッファ割れへの対応順序](references/calendar-and-report.md#バッファ割れへの対応順序) に沿って手段を検討し、[報告書形式](references/calendar-and-report.md#報告書形式) に従って、納付の山、割れる月と不足額、確認すべき事項、期限のある行動を示す。

## 判断上の制約

- 税率、料率、納期限、中間納付の要否と回数、納期の特例の可否を推測しない。当日の一次情報で確認し、確認日と出典を残す。確認できないものは `unknown` のままにする。
- `unknown` を0に置き換えない。金額が不明な納付を含む月と、それ以降の月の残高は計算せず `null` とする。どの月まで判定できるかを必ず併記する。
- バッファ割れは警戒事象であり、支払不能の判定でも、納付を遅らせてよい根拠でもない。
- 従業員数、賞与、標準報酬月額の定時決定・随時改定、料率改定で社会保険料は変動する。単月の額を横引きして12か月分としない。
- 概算・見積の納付額は `estimated` のまま扱い、確定額と一つの合計に混ぜない。
- 納付区分の想定は事業者プロフィールから機械的に導いたものにすぎない。想定に無い納付が存在する可能性を常に残し、`missing_categories` を「無い」と読み替えない。
- 消費税、法人税・地方税、源泉所得税、住民税、社会保険、労働保険は所管も納期限も異なる。一つの納付を確認したことをもって他を確認済みとしない。

## 権限境界

このスキルは、資金繰りの見通し、確認事項の一覧、行動案を作るだけである。納付、口座振替の設定、e-Tax・eLTAX・電子申請の送信、税務署・年金事務所・労働局・市区町村・税理士・社会保険労務士への連絡、猶予や分割納付の申請、資金移動を自動実行しない。実行直前に、対象、金額、期限、影響、取り消し可能性を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
