---
name: business-continuity-check
description: Map critical people, customers, vendors, systems, facilities, data, and processes; compare recovery time with tolerated downtime; and expose single points and blast radius. Use when prioritizing continuity tests and fallback plans; do not use as incident-response authorization.
license: MIT
metadata:
  author: ficilcom
---

# 事業継続性チェック

人、顧客、ベンダー、システム、設備、データ、業務の依存関係を可視化し、停止許容時間、想定復旧時間、検証済み代替、影響範囲から優先的に備える単一障害点を特定する。

## 進め方

1. [インテークと分析方法](references/intake-and-method.md)を読み、重要な顧客提供・資金・法的義務から逆向きに依存関係を集める。
2. 各依存に重要度、停止確率、最大許容停止時間、想定復旧時間、所有者、代替、依存先を置き、`confirmed`、`reported`、`estimated`、`unknown` に分ける。
3. [計算モデル](references/calculation-model.md)に従い匿名化JSONを作り、スキルのルートで `python3 scripts/analyze_continuity.py <input.json>` を実行する。
4. 復旧超過、検証済み代替の欠如、所有者不在、直接・間接の影響範囲を確認する。モデル順位を障害発生予測にしない。
5. [報告書形式](references/report-format.md)で優先リスク、暫定手順、復旧条件、検証日、改善所有者、再評価日を示す。

## 判断上の制約

- 文書上の代替を「使える代替」とみなさず、権限、データ、連絡先、能力、実行時間を実地に検証する。
- 発生確率が不明でも重大な単一障害点を無視しない。不明をゼロへ置き換えず、定量順位とは別に扱う。
- 個人名、顧客名、認証情報、復旧鍵など機密情報を配布可能な成果物へ含めない。必要なら匿名識別子と安全な保管場所を使う。

## 権限境界

本番停止、切替、復元、顧客・当局連絡、契約変更、データ操作を自動実行しない。テストも対象、時間、影響、復元条件、承認者を示し、利用者の明示承認を得る。
