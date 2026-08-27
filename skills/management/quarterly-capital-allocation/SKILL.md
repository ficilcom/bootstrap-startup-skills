---
name: quarterly-capital-allocation
description: Compare quarterly uses of scarce cash through user-defined proposal portfolios, base and downside cash paths, buffer resilience, payback, strategic fit, and reversibility. Use when a bootstrapped business must choose which investments to fund, defer, stage, or test; do not use as valuation advice or authorization to spend.
license: MIT
metadata:
  author: ficilcom
---

# 四半期資本配分

限られた現金を、採用、販売、製品、在庫、設備、業務改善などの候補へどう配分するかを、基準・悲観の資金経路、回収、戦略適合、可逆性、依存条件で比較する。定量効果だけを最大化せず、守るべきガードレールと学習価値を含めて判断する。

## 進め方

1. 最初に [インテークと判断方法](references/intake-and-method.md) を読み、現在現金、最低バッファ、基礎入出金、既存コミット、四半期目標、投資候補を確認する。
2. 一つの基準日、単一通貨、月次期間、基準資金見通しを固定する。既に決定済みの支出と新しい候補を混ぜず、事実を `confirmed`、`reported`、`estimated`、`unknown` に分ける。
3. 各候補に初期費用、月次費用、基準便益、悲観便益・追加費用、戦略適合、可逆性、依存関係、重複し得る便益を置く。便益は現金効果として説明できるものだけを計算し、能力・学習・リスク低下は別表示する。
4. [計算モデル](references/calculation-model.md) に従い、利用者が比較したいポートフォリオを明示したJSONを作る。スキルのルートで `python3 scripts/compare_allocations.py <input.json>` を実行する。
5. 基準・悲観の両方で最低バッファを維持するか、回収時期、依存条件、便益重複を確認する。自動出力の「配分可能」は支出承認や最適性ではない。
6. [報告書形式](references/report-format.md) で、`fund`、`stage`、`test`、`defer`、`reject` の候補、判断期限、再評価条件を示す。

## 判断上の制約

- 現金バッファを使い切る計画を、期待便益だけで正当化しない。悲観ケースで守れない候補は、規模縮小、段階化、条件付き実行を検討する。
- 便益の二重計上、候補間依存、組織能力、不可逆性を別に評価する。回収期間が短いだけで戦略優先度を決めない。
- 不明入力を悲観値やゼロへ置き換えない。結果を変える不明点には最小テスト、見積、契約確認、再判断日を置く。

## 権限境界

支出、採用、発注、契約、送金、広告変更、ツール導入、在庫購入を自動実行しない。実行直前に候補、金額、相手、条件、資金影響、ロールバック可能性を示して利用者の明示承認を得る。
