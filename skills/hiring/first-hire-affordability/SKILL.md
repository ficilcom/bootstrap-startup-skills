---
name: first-hire-affordability
description: Determine whether a bootstrapped business can afford its first employee by modeling fully loaded employment cost, cash buffer and runway, downside and delayed-start scenarios, and the earliest defensible hiring date. Use before opening a first role or committing to a first employee; do not use as legal, tax, payroll, or employment-law advice.
license: MIT
metadata:
  author: ficilcom
---

# 最初の採用の資金余力

最初の従業員を採用した後も、必要な現金バッファを維持して運営できるかを現金ベースで判定する。給与だけでなく、事業主負担、福利厚生、採用、一時的な設備・ソフトウェア、オンボーディング、生産性立上がり、管理時間、退職・解雇等の偶発的一時費用を分けて見積もる。結論は `hire_now`、`conditional`、`defer`、`unaffordable`、または重要情報が不明な `indeterminate` とし、最短開始月と実行条件を示す。これは採用判断の運営分析であり、雇用契約、支払能力、労務・税務・法務上の専門判断ではない。

## 進め方

1. 最初に [インテーク](references/intake.md) を読み、提出済みの銀行残高、資金繰り、給与見積、採用計画を確認する。根拠は `confirmed`、`reported`、`estimated`、`unknown` に分け、`unknown` をゼロにしない。
2. 少なくとも `base`、`downside`、`delayed` を作る。`base` は根拠のある中心見通し、`downside` は回収遅延・売上低下・費用増など意思決定を変え得る不利な見通し、`delayed` は開始延期案とする。雇用開始月、既存事業の月次入出金、採用後の便益立上がりをそれぞれ明示する。
3. [計算モデルとJSON契約](references/calculation-model.md) を読み、必要最小限に匿名化した単一通貨のJSONをスキル外へ作る。賃金に会社負担を重複計上せず、各コストの現金支払時期を区別する。
4. スキルのルートで `python3 scripts/calculate_affordability.py <input.json>` を実行する。検証エラーを推測で埋めない。開始現金、最低バッファ、通常の入出金、または雇用コストの重要値が `unknown` なら、数値結論は `indeterminate` とし、不足情報を報告する。
5. [判断ルール](references/decision-rules.md) を読み、スクリプトの判定を事業上の便益、採用リードタイム、確認済みでない前提に結び付ける。開始月は、base と downside の両方でバッファを維持する最も早い月を基準にし、単なる希望開始日を「賄える」と扱わない。
6. [報告書形式](references/report-format.md) を読み、シナリオ比較、採用前後の現金、ランウェイ、総雇用コスト、便益回収、最短開始月、撤退条件、不確実性を利用者の言語で報告する。

## 判断上の制約

- `minimum_cash_buffer` は雇用コストではない。期末現金がバッファを下回ることと、現金が負になることを別々に扱う。予測期間内に割れなければ、未検証の将来まで安全だと断定しない。
- 便益立上がりは、採用で直ちに売上が増えると仮定しない。採用効果は月次の現金便益として根拠・時期を示し、雇用コストと別表示する。便益が総コストを回収しない場合も隠さない。
- 所得税源泉、社会保険、労働保険、福利厚生の法定要件、雇用区分、解雇・退職コストは法域・契約・時点に依存する。結論を変える場合だけ、当日の政府・公的機関等の権威ある一次情報を確認し、確認日と出典を記す。専門家の判断を代替しない。
- `conditional` は条件を満たす前の採用承認ではない。必要な現金改善、根拠確認、採用開始日の再計算を、実行条件として具体化する。

## 権限境界

求人公開、候補者探索・連絡、面接設定、オファー、雇用契約、給与設定・支払、機器購入、ベンダー契約、解雇・退職手続、外部への連絡は自動実行しない。各行為の直前に、利用者の明示的な承認を得る。このスキルの利用承認は、それら外部行為の承認ではない。
