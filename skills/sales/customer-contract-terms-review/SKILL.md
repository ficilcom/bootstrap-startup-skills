---
name: customer-contract-terms-review
description: Review the commercial terms of a contract or quotation the business is selling under by converting the billing schedule, acceptance lag, and payment terms into a month-by-month cash path, reporting the peak amount the business funds itself and the month it occurs, measuring liability cap, termination, and auto-renewal exposure against user-defined limits, and ordering negotiation priorities by exposure. Use before agreeing commercial terms with a customer or when a deal's payment terms threaten cash; do not use it to judge clause validity, enforceability, or legal risk, to decide price level, or to send, sign, or answer anything on the customer's side.
license: MIT
metadata:
  author: ficilcom
---

# 顧客契約条件レビュー

自社が売り手となる契約・見積について、請求分割、検収、支払サイトから現金のタイミングを組み、契約完了までに自社が持ち出す立替ピーク額と発生月を出す。責任上限、解約予告、自動更新の露出を利用者が定めた上限と突き合わせ、交渉対象を露出額順に並べる。条項の有効性や適法性の判断ではなく、価格水準の判断でもない。

## 進め方

1. 最初に [インテークと方法](references/intake-and-method.md) を読み、契約額、期間、請求分割、支払サイト、検収日数、提供コストの月次配分、利用者が許容する上限を確認する。顧客名、担当者名、契約番号を入力へ含めない。
2. 契約書に書かれた条件を `confirmed`、交渉中の合意を `reported`、実務上の見込みを `estimated` に分ける。契約書に記載がない条件をゼロや有利な値で埋めない。
3. [計算モデル](references/calculation-model.md) に従いスキル外へ匿名化JSONを作り、スキルのルートで `python3 scripts/review_contract_terms.py <input.json>` を実行する。責任上限、解約、自動更新、知財、再委託を見る場合は `analysis_mode` を `advanced` にする。
4. 立替ピークが自社の現金で耐えられるかを先に確認する。耐えられない場合は、価格ではなく請求分割と支払サイトで改善できるかを見る。
5. [条項別の論点と交渉の代替案](references/terms-checklist.md) で、抵触した上限に対応する条項へ交渉を絞り、条項ごとに代替案を1つ用意する。
6. [報告書形式](references/report-format.md) で、現金タイミング、露出、条項フラグ、交渉優先順位、立替が耐えられない場合の選択肢、弁護士確認が必要な条項を示す。

## 判断上の制約

- 責任上限が「無制限」と「契約に記載がなく不明」を同一視しない。不明は結果を変える不明点として確定させる。
- 立替ピークは自社の最低現金バッファと突き合わせて評価する。契約単体の採算だけで受注可否を決めない。
- 上限は利用者が定めたものだけを使う。普遍的に適正な支払サイトや責任上限を置かない。
- 条項の有効性、適法性、紛争時の見通しを判定しない。判断が必要な条項は弁護士確認の対象として分けて示す。

## 権限境界

契約締結、見積提出、条件の回答、顧客連絡、値引きの提示、CRM更新を自動実行しない。実行直前に相手、提示する条件、金額、期限、資金影響、応諾されなかった場合の対応を示して利用者の明示承認を得る。このスキルの利用承認は外部行為の承認ではない。
