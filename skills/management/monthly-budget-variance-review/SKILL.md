---
name: monthly-budget-variance-review
description: Review a month's budget-to-actual variances by ruling out data quality, definition changes, and timing before attributing anything to mix or real business change, decomposing material revenue and cost variances into price, volume, and mix effects, and turning only the surviving explanations into corrective actions. Use for a monthly operating review that sits between weekly reviews and quarterly capital allocation; do not use it as an accounting close, a KPI dashboard, or a substitute for reconciled books.
license: MIT
metadata:
  author: ficilcom
---

# 月次予実差異レビュー

一か月の予実差異について、原因を断定する前に データ品質、定義変更、タイミング を順に排除し、残った差異だけを構成変化と事業の実変化に帰属させ、価格・数量・ミックスに分解して是正行動につなげる。これは月次の運営レビューであり、決算の締め、KPIダッシュボード、整合の取れた帳簿の代替ではない。

## 進め方

1. 最初に [インテークと分析方法](references/intake-and-method.md) を読み、試算表、予算、前月レビュー、請求・回収明細、数量と単価のデータを質問より先に確認する。このスキルは帳簿を締めない。締まっていない数字は締まっていないものとして扱う。
2. 対象期間、比較基準（予算・見通し・前年同月・前月）、通貨、締め状態（速報値か確定値か）を一つに固定する。週次レビュー（`skills/management/weekly-founder-review/`）を運用している場合は、そこで扱った異常候補のうち月次の勘定科目に現れたものを引き継ぐ。
3. [重要性の決め方](references/intake-and-method.md#重要性の決め方) に従い、金額基準と率基準の組合せをレビュー開始前に固定する。分析を見てから閾値を動かさない。
4. 各行について、[切り分けの順序](references/intake-and-method.md#切り分けの順序) の5段階を順に確認し、各段階を `cleared`、`explains`、`unresolved`、`not_checked` のいずれかで記録する。前の段階が未解決のまま、後の段階を原因と記録しない。
5. [計算契約](references/intake-and-method.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/analyze_budget_variance.py <input.json>` を実行する。出力は分析であり、会計システムや予算の更新を行わない。
6. 重要な売上・原価の差異は [価格・数量・ミックス分解](references/intake-and-method.md#価格数量ミックス分解) を使って要因に分ける。ミックスは残差として算出されるため、ミックスが大きいときはセグメント定義と分母を先に疑う。
7. [是正アクション](references/intake-and-method.md#是正アクション) に従い、帰属した段階ごとに取るべき手当てを分ける。タイミング差異には再確認日を、構造的な実変化には `skills/management/quarterly-capital-allocation/` へ渡す提案候補を置く。
8. [報告書形式](references/intake-and-method.md#報告書形式) に従い、説明できた差異、説明できていない差異、切り分け違反、次月の行動を示す。

## 判断上の制約

- 差異の原因を、前の段階が未解決のまま後の段階へ飛ばして断定しない。データ品質と定義変更が未確認の差異を、事業の実変化として扱わない。
- 重要性の閾値をレビューの途中で変えない。閾値は事前に、金額基準と率基準の組合せとして固定する。閾値が示されていない行を、勝手な基準で重要でないと判定しない。
- 予算0の行に増減率を出さない。金額差異と、比較できない理由を示す。予算0で実績があるものは、金額の大小によらず未予算の支出・収益として扱う。
- ミックス効果は残差として算出しており、価格と数量の測定誤差を吸収する。ミックスが大きい場合は、結論を出す前にセグメント定義、分母、対象範囲を確認する。
- セグメントが行全体を覆っていない場合、分解は行の一部にしか当たらない。覆っていない金額を明示し、行全体の説明として使わない。
- タイミング差異は是正対象ではなく、再確認日の対象である。翌月に戻るはずの差異に恒久的な費用削減を当てない。
- 速報値の予実を確定値として扱わない。締め状態が速報のとき、結論はすべて暫定とする。
- 金額が不明な行がある限り、レビュー全体を「説明済み」としない。重要性は金額なしには判定できない。

## 権限境界

このスキルは、分析、是正案、次月の行動案を作るだけである。会計システム、予算、KPIツール、CRMの更新、価格・広告・契約・発注・支払の変更、従業員・顧客・取引先への連絡を自動実行しない。実行直前に、対象、内容、金額、時期、担当、影響、取り消し可能性を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
