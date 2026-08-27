---
name: process-bottleneck-audit
description: Diagnose where an operating process loses throughput through capacity limits, work-in-progress, waiting, blocking, and rework, then prioritize measurable improvements. Use when delivery is late, queues are growing, or demand exceeds operating capacity; do not use to automate production changes or judge employee performance from activity counts alone.
license: MIT
metadata:
  author: ficilcom
---

# 工程ボトルネック監査

業務工程の処理能力、流入・完了、仕掛り、待ち、阻害、手戻りを同じ観測期間で比較し、全体スループットを制約している候補と最小の改善実験を特定する。個人の忙しさや稼働率だけを生産性とみなさない。

## 進め方

1. 最初に [インテークと診断方法](references/intake-and-method.md) を読み、依頼・受注から完了までの工程、入口・出口、単位、期間、仕掛り、作業時間、待ち理由、手戻りを確認する。
2. 一つのプロセス、同じ期間、同じ完了単位を固定する。流入、完了、開始時仕掛り、利用可能時間、単位作業時間、待ち時間を `confirmed`、`reported`、`estimated`、`unknown` に分ける。
3. [計算モデル](references/calculation-model.md) に従い匿名化JSONを作り、スキルのルートで `python3 scripts/analyze_process.py <input.json>` を実行する。能力不足、仕掛り、待ち、利用率、初回合格率を別々に確認する。
4. 出力の候補順を確定原因とせず、現場記録、依存先、バッチ、承認、切替、品質、変動需要で検証する。最も忙しい工程ではなく、全体完了を増やす変更を優先する。
5. [報告書形式](references/report-format.md) で、制約候補、根拠、データ品質、改善実験、期待スループット、ガードレール、停止条件を示す。

## 判断上の制約

- 利用率100%を目標にしない。変動、保守、例外処理、品質確認に必要な余力を無視すると待ちが増える。
- `work time` と `wait time`、`throughput` と `activity`、`rework` と新規完了を分ける。仕掛りの削減だけで需要充足と断定しない。
- 工程間で単位、期間、完了条件が違うなら順位付けしない。推定作業時間は感度として扱い、測定値のように表示しない。

## 権限境界

このスキルは工程変更案、実験計画、SOP案を作るだけである。人員配置、勤務、顧客納期、システム設定、自動化、外注、発注、品質基準を自動変更しない。実行直前に対象、影響、担当、期間、ロールバック条件を示して明示承認を得る。
