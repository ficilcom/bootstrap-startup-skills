---
name: accounts-receivable-control
description: Diagnose why invoiced revenue is not becoming cash by aging receivables, identifying customer exposure, separating disputes and payment commitments, and prioritizing evidence-based collection actions. Use when overdue invoices or uncertain collections threaten cash planning; do not use for statutory accounting, legal debt enforcement, or automatic customer contact.
license: MIT
metadata:
  author: ficilcom
---

# 売掛金・回収管理

請求済み売上が現金化されない原因を、請求書単位の残高、経過日数、顧客集中、紛争、支払約束、資金への影響に分け、回収の確認順序と次の行動を作る。これは運営上の回収管理であり、会計上の貸倒判定、債権の法的有効性、強制回収の助言ではない。

## 進め方

1. 最初に [インテークと判断方法](references/intake-and-method.md) を読み、請求書、入金、契約、検収、支払約束、紛争記録を質問より先に確認する。顧客名は匿名IDにし、不要な連絡先・口座・認証情報を収集しない。
2. 基準日、単一通貨、請求・入金の対象範囲を固定する。請求額、入金額、支払期日、約束日、紛争状態を `confirmed`、`reported`、`estimated`、`unknown` に区別し、`unknown` をゼロや回収不能へ置き換えない。
3. [計算モデル](references/calculation-model.md) に従って匿名化JSONをスキル外に作り、スキルのルートで `python3 scripts/analyze_receivables.py <input.json>` を実行する。年齢表、顧客別残高、明示された支払約束、資金影響を確認する。
4. 回収優先順位は、金額だけでなく、期限超過、約束不履行、紛争、顧客集中、契約・検収の未解決、相手先の支払手続、資金バッファへの影響で決める。根拠のない回収確率や一律の督促スコアを作らない。
5. [報告書形式](references/report-format.md) で、確定残高と不明残高、年齢表、支払約束、顧客別露出、資金の谷、内部確認、外部連絡案を分ける。各行動に担当、期限、必要資料、停止・エスカレーション条件を置く。

## 判断上の制約

- `issued`、`due`、`overdue`、`disputed`、`promised`、`collected` を混同しない。請求済みでも検収・契約条件が未解決なら、単純な督促より先に原因を確認する。
- 確認済みの支払約束だけを短期資金計画へ加える。申告・推定の入金は別表示し、全売掛金を将来現金として扱わない。
- 入金遅延日数は回収不能の判定ではない。法域、契約、倒産、時効、貸倒、税務処理が判断を左右する場合は、当日の権威ある一次情報または専門家を確認する。

## 権限境界

このスキルは、内部確認表、回収順序、連絡文面案、エスカレーション案を作るだけである。顧客への連絡、督促、請求書再発行、支払条件・契約変更、サービス停止、債権回収委託、法的手続、会計処理を自動実行しない。実行直前に対象、内容、金額、期限、影響を示し、利用者の明示承認を得る。
