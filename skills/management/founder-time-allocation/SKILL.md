---
name: founder-time-allocation
description: Review a founder's time using observed hours, founder necessity, value, leverage, and delegation readiness. Use when deciding what to protect, delegate, reduce, automate, or stop; do not use as authorization to change calendars, roles, or employment arrangements.
license: MIT
metadata:
  author: ficilcom
---

# 創業者の時間配分レビュー

創業者の限られた時間を観測し、本人が担うべき高レバレッジ活動と、委譲・削減・自動化の候補を分ける。忙しさではなく、事業上の価値と創業者である必要性を基準にする。

## 進め方

1. [インテークと分類方法](references/intake-and-method.md)を読み、代表週または複数週の実績、役割、固定予定、意思決定権、委譲先候補を集める。
2. 活動を成果単位へまとめ、時間を `confirmed`、`reported`、`estimated`、`unknown` に分ける。予定表だけでなく実績を優先する。
3. 創業者必須、価値、レバレッジ、委譲準備度を0〜5で評価する。高得点を作るために定義を後から変えない。
4. [計算モデル](references/calculation-model.md)に従い匿名化JSONを作り、スキルのルートで `python3 scripts/analyze_founder_time.py <input.json>` を実行する。
5. [報告書形式](references/report-format.md)で守る時間、委譲候補、削減候補、回収可能時間、移行実験、再評価日を示す。

## 判断上の制約

- 高工数だけで委譲しない。顧客信頼、資金、戦略、採用、品質など創業者固有の責任を確認する。
- 委譲可能性は「他人でもできる」だけでなく、手順、品質基準、権限、情報、受け手の能力で判定する。
- 不明な時間をゼロにせず、観測期間の季節性や緊急対応を恒常業務と混同しない。

## 権限境界

会議の削除、カレンダー変更、権限移譲、採用・外注、業務停止を自動実行しない。対象、受け手、品質条件、移行期間、ロールバック条件について利用者の明示承認を得る。
