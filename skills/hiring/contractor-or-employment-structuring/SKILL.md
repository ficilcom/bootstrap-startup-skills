---
name: contractor-or-employment-structuring
description: Organize how a contractor engagement actually operates against recognized factors - direction and control, work discretion, time and place constraints, remuneration character, exclusivity, substitutability, and equipment burden - preserving each factor's evidence state, sizing retroactive cost from user-supplied assumptions only, and testing which employment-like factors a proposed change actually removes. Use when an ongoing outsourcing or contractor arrangement may operate like employment and the founder needs the issues and exposure laid out; do not use it to determine classification, to substitute for an administrative or judicial decision, to calculate statutory insurance or tax liability, or to change, terminate, or notify anything.
license: MIT
metadata:
  author: ficilcom
---

# 業務委託と雇用の線引き

業務委託として運用している関係の実態を要素ごとに整理し、雇用的と観測された要素、未観測の要素、利用者が置いた前提での遡及コスト規模、是正案が実際に消す要素を示す。該当性の判定ではなく、行政・司法の判断を代替するものでもない。

## 進め方

1. 最初に [インテークと方法](references/intake-and-method.md) を読み、契約形式、月額、経過月数、残り見込み月数と、実際の働き方を確認する。氏名、保護属性、個人が特定できる情報を入力へ含めない。
2. [判断要素の定義と観測例](references/classification-factors.md) に沿って、7つの要素を1件ずつ観測する。契約書の文言ではなく運用の実態から埋め、契約書との食い違いは食い違いとして記録する。
3. 観測を `independent`、`mixed`、`employment_like`、`unknown` に分け、証拠を `confirmed`、`reported`、`estimated`、`unknown` に分ける。確認していない要素を独立的と推定して埋めない。
4. [計算モデル](references/calculation-model.md) に従いスキル外へ匿名化JSONを作り、スキルのルートで `python3 scripts/assess_engagement_structure.py <input.json>` を実行する。遡及コストと是正案を見る場合は `analysis_mode` を `advanced` にする。
5. 是正案は、どの雇用的要素を実際に消すかで評価する。全案を実行しても残る要素と、その要素についての専門家確認の要否を確認する。
6. [報告書形式](references/report-format.md) で、要素別の観測、遡及コストと置いた前提、是正案と事業への影響、次の行動を示す。専門家へ確認すべき論点は期限付きで分けて書く。

## 判断上の制約

- 要素の多数決や合計点で結論を出さない。要素ごとの観測状態と証拠状態を保持したまま報告する。
- 該当性を判定せず、行政・司法の判断を代替しない。判断が必要な論点は社会保険労務士または弁護士へ確認する条件として示す。
- 遡及コストは利用者が置いた前提の算術であり、保険料額、税額、割増賃金額の決定ではない。前提の値と根拠を必ず併記する。
- 契約書の文言変更だけを是正として扱わない。運用が変わらなければ要素の観測状態は変わらない。
- 事業への影響がない是正案は、実態を変えていない可能性が高いものとして扱う。

## 権限境界

契約の変更、終了、更新停止、遡及的な手続、支払、本人への通知、専門家への依頼、行政への照会を自動実行しない。実行直前に対象、変更内容、時期、費用、相手方への影響を示して利用者の明示承認を得る。このスキルの利用承認は外部行為の承認ではない。
