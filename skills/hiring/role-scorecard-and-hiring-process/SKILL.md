---
name: role-scorecard-and-hiring-process
description: Structure a role scorecard and compare anonymized hiring candidates when a founder needs evidence-based outcomes, competencies, must-have gates, work samples, interviews, references, and a defensible advance, hold, or stop decision. Do not use for automatic candidate contact or employment decisions.
license: MIT
metadata:
  author: ficilcom
---

# 役割スコアカードと採用プロセス

役割の期待成果、能力、必須条件を先に固定し、候補者の証拠スコアと採用ゲートを分けて比較する。

## 進め方

1. [インテークと方法](references/intake-and-method.md) を読み、役割ID、成果、能力、must、重み、最低評価を候補者を見る前に定義する。
2. 候補者は匿名IDだけで扱い、評価値を `confirmed`、`reported`、`estimated`、`unknown` に分ける。保護属性や不要な個人情報を入力しない。
3. coreでは評価とmustゲートを比較する。ワークサンプル、構造化面接、リファレンス、報酬承認などの工程ゲートと重み感度を見る場合はadvancedを使う。
4. [計算モデル](references/calculation-model.md) に従いスキル外へJSONを作り、`python3 scripts/evaluate_hiring_process.py <input.json>` を実行する。
5. エラーは入力で訂正する。未評価をゼロ・平均点にせず、評価者間の不一致を単一値で隠さない。
6. [報告書形式](references/report-format.md) に従い、スコア順位、must・工程ゲート、反証、追加検証、停止条件を分ける。

## 判断上の制約

- must失敗を高い平均点や他の能力で救済しない。must不明は `conditional` とする。
- `evidence_order` は全項目が揃った加重評価だけであり、採用順位や適法性を保証しない。
- 重みで順位が変わる場合は確定順位にせず、役割設計または追加証拠を再確認する。
- 一貫した質問、評価尺度、独立評価を使い、候補者ごとに基準を変えない。

## 権限境界

候補者連絡、面接設定、不採用通知、リファレンス照会、オファー、報酬提示、HRシステム更新を実行する直前に利用者の明示承認を得る。
