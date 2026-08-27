---
name: grant-execution-and-reporting
description: Plan post-award grant execution by reconciling committed spend against the approved cost breakdown, checking procurement and evidence gaps that create clawback exposure, and sizing the bridge financing needed and the date it must be arranged, because the subsidy is paid in arrears after the performance report. Use after a grant decision notice is issued and before spending or reporting; do not use it to determine expense eligibility, to file a report, or to authorize spending or borrowing.
license: MIT
metadata:
  author: ficilcom
---

# 補助金の交付後実行と実績報告の準備

交付決定後について、確定した経費区分に対する発注・支払の状況、返還につながる不備、証憑の欠落、そして補助金が後払いであることによって必要になるつなぎ資金の額と手当ての期限を整理する。これは実行計画であり、経費の対象・対象外の判定、実績報告の提出、支出や借入の承認ではない。

## 進め方

1. 最初に [インテークと義務](references/intake-and-obligations.md) を読み、交付決定通知、交付要綱、実績報告の手引き、経費区分表を質問より先に確認する。[交付決定後に確定する事実](references/intake-and-obligations.md#交付決定後に確定する事実) の当日再確認リストに従い、経費区分の定義、相見積の要否と件数、支払方法の制限、証憑の種類と保存期間、変更承認が必要な事象、財産処分制限を一次情報で確認する。
2. **経費の対象・対象外を自分で判定しない。** 判定は交付要綱と事務局に属する。各経費に、利用者が確認した状態（`confirmed` / `likely` / `unclear` / `ineligible` / `not_applicable`）を付けるだけにする。
3. [経費区分と証憑の対応](references/intake-and-obligations.md#経費区分と証憑の対応) に従い、経費ごとに必要な証憑を洗い出し、保有・未入手・欠落・不明を区別する。後から補えない証憑と、発生後に是正できる証憑を分ける。
4. [返還リスクの型](references/intake-and-obligations.md#返還リスクの型) を使い、交付決定前の発注、事業期間外の支払、相見積の不足、支払方法の制限、証憑の不備を個別に確認する。
5. [計算契約](references/intake-and-obligations.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/plan_grant_execution.py <input.json>` を実行する。出力は実行計画であり、発注も支払も報告も行わない。
6. [後払いの資金繰り](references/bridge-finance-and-report.md#後払いの資金繰り) を読み、支出から入金までのキャリー期間を構成要素に分ける。入金日に公式な根拠がない場合は `unknown` とし、[つなぎ資金の手当て](references/bridge-finance-and-report.md#つなぎ資金の手当て) に従って入金なしの資金繰りで必要額を出す。
7. 計画を変える必要が生じた場合は [変更手続](references/bridge-finance-and-report.md#変更手続) を確認し、事前承認が必要な事象を実施前に特定する。[報告書形式](references/bridge-finance-and-report.md#報告書形式) に従い、補助金額の幅、返還リスク、証憑のギャップ、つなぎ資金の必要額と手当て期限を示す。

## 判断上の制約

- 経費の対象・対象外を自分で判定しない。このスキルは利用者が確認した状態を集計するだけである。
- 入金日を推測しない。公式な根拠のない入金日は `unknown` とし、入金がない前提の資金繰りで必要額を示す。**後払いである以上、入金日の楽観は資金ショートに直結する。**
- 確定額は実績報告後の検査で減額され得る。確認済みのみの補助金額、見込みを含めた額、未確認を含めた額を**別々に**示し、合算した一つの見込み額を作らない。
- 相見積、支払方法、支払時期、証憑の不備には、後から補えないものがある。発生前に確認すべき項目と、発生後に是正できる項目を分ける。
- 交付決定前の発注・支出、事業期間外の支払、無承認の計画変更は、返還につながる典型例である。個別に示し、まとめて「軽微」と扱わない。
- 承認額を超えて発注した分は自己負担であり、後から承認されると仮定しない。
- 必要な相見積の件数が不明な場合、1件や2件を既定として補わない。不明のまま確認事項として残す。
- 補助金額の見込みを、それが入るものとして他の資金計画に組み込まない。

## 権限境界

このスキルは、実行計画、確認事項の一覧、資金手当ての案を作るだけである。発注、契約、支払、実績報告や計画変更承認申請の提出、事務局・金融機関・専門家への連絡、つなぎ資金の申込み、証憑の外部共有を自動実行しない。実行直前に、行為、相手先、金額、期限、返還・法的影響、取り消し可能性を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
