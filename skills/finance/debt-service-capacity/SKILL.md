---
name: debt-service-capacity
description: Measure whether existing and proposed borrowing is serviceable by rebuilding the repayment schedule, calculating debt service coverage, repayment years, additional borrowing headroom under user-supplied policy floors, and the monthly cash path, and by listing the conditions that make a restructuring discussion with the lender worth starting. Use after a loan-readiness diagnosis, before requesting new debt, or when repayments are straining cash; do not use it to predict approval, set interest rates, or decide unilaterally to stop or reduce payments.
license: MIT
metadata:
  author: ficilcom
---

# 返済余力診断

既存借入と検討中の借入について、返済予定表を再構築し、返済余力、債務償還年数、追加借入余地、月次の資金繰りを同じ前提で示す。これは返済の可否と余地を測る診断であり、審査結果の予測、適用金利の提示、条件変更の推奨、返済停止の判断ではない。

## 進め方

1. 最初に [インテークと算定方法](references/intake-and-method.md) を読み、返済予定表、借入金明細、決算書、試算表、保証・担保の状況、契約書の特約を質問より先に確認する。`bank-loan-readiness` を既に実施している場合は、[引き継ぎ](references/intake-and-method.md#インテーク) に従って資料台帳と返済予定を再利用し、適格性ルーブリックを再実行しない。
2. 基準日、通貨、見通し月数、キャッシュフローの対象期間を一つに固定する。期間の異なる決算書と試算表を混ぜず、正規化調整は項目ごとに理由と符号を残す。
3. 重要な事実と仮定を `confirmed`、`reported`、`estimated`、`unknown` に区別する。`unknown` を0や平均値に置き換えない。金利、残高、残期間、据置期間は契約書と返済予定表の記載を優先する。
4. 判定基準となる DSCR の下限と債務償還年数の上限は、利用者または金融機関が示した値だけを `policy` に入れる。示された基準がない場合は基準なしのまま進め、合否を判定しない。
5. [計算契約](references/intake-and-method.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/calculate_debt_capacity.py <input.json>` を実行する。出力は診断材料であり、金融機関への申込みや返済条件の変更を行わない。
6. [判定と閾値](references/intake-and-method.md#判定と閾値) を使い、返済余力、償還年数、追加借入余地の拘束条件、下振れ時の耐性を読む。基準に届かない結果が出た場合は、[リスケ検討の順序](references/intake-and-method.md#リスケ検討の順序) に沿って、条件変更より先に検討すべき手段から確認する。
7. [報告書形式](references/intake-and-method.md#報告書形式) に従い、現状の返済余力、拘束している制約、下振れ時の資金繰り、金融機関と話す前に用意すべき資料と論点を示す。

## 判断上の制約

- DSCR と債務償還年数の合格ラインは、業種、金融機関、保証、担保、事業段階で異なる。利用者または金融機関が示した基準以外を合格基準として使わない。基準がなければ数値を示すにとどめ、良し悪しを断定しない。
- 追加借入余地の2つの制約（返済余力と債務償還年数）を一つの数値に合成しない。制約が異なる答えを出す場合は両方を示し、拘束している側を明示する。
- キャッシュフローが0以下のときに債務償還年数を算出しない。負の年数や無限大の年数を出さない。
- 据置期間中の返済額を、据置明けの返済額として扱わない。据置が終わる月と、その月から増える返済額を分けて示す。
- 簡易キャッシュフローと営業キャッシュフローを平均しない。両方ある場合は差分と、どちらを基礎に置いたかを示す。
- 下振れ倍率はキャッシュ創出にのみ適用し、契約上確定している返済額や期首残高には適用しない。既に資金流出の月を、下振れによって改善させない。
- リスケジュールは資金繰りの技術的な解ではなく、信用保証、追加調達、取引関係に影響する。このスキルは条件の充足状況を示すだけで、実施を推奨しない。

## 権限境界

このスキルは、分析、資料案、金融機関と話すための論点整理を作るだけである。金融機関、信用保証協会、税理士、認定支援機関への連絡、条件変更や借換えの申込み、返済の停止・減額、契約締結、送金を自動実行しない。実行直前に、相手先、内容、金額、時期、影響、取り消し可能性を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
