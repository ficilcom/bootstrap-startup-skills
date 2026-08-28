---
name: offer-portfolio-review
description: Compare products and services using contribution, capacity, demand evidence, downside scenarios, offer relationships, strategic fit, and exit gates. Use when deciding which offers to grow, repair, test, bundle, hold, or consider retiring; do not use as authorization to discontinue an offer or change customer commitments.
license: MIT
metadata:
  author: ficilcom
---

# 商品・サービス構成レビュー

商品・サービスごとの利益と希少な提供能力の消費を揃え、伸ばす、直す、検証する、束ねる、終了を検討する対象を分ける。売上規模だけで判断せず、需要の証拠、戦略適合、顧客・契約への影響を別に扱う。

## 進め方

1. [インテークと判断方法](references/intake-and-method.md)を読み、同じ期間・通貨・変動費範囲で商品別の売上、変動費、提供工数、需要証拠、戦略適合を集める。
2. 入力を `confirmed`、`reported`、`estimated`、`unknown` に分ける。需要、商品間関係、感度、退出制約まで判断する場合は `advanced` を選び、[判断ルール](references/decision-rules.md)を読む。共通費を根拠なく商品へ割り振らない。
3. [計算モデル](references/calculation-model.md)に従い匿名化JSONを作り、スキルのルートで `python3 scripts/analyze_offer_portfolio.py <input.json>` を実行する。
4. 貢献利益、利益率、提供1時間当たり貢献、能力消費、需要、シナリオ、商品間関係、戦略適合、退出ゲートを並べる。経済順位と判断シグナルを推奨や自動実行にしない。
5. [報告書形式](references/report-format.md)で `grow`、`repair`、`test`、`bundle`、`hold`、`retire candidate` を示し、必要な検証と再判断日を置く。

## 判断上の制約

- 過去売上だけで需要を推定せず、受注率、更新、待ち行列、失注理由、顧客要望を区別する。
- 低利益でも入口商品、信頼形成、他商品の販売に効く場合がある。効果を証拠なしに利益へ足さず、別の戦略仮説として検証する。
- 終了判断では既存契約、返金、移行、顧客連絡、ブランド影響を確認する。不明値をゼロへ置き換えない。

## 権限境界

価格、提供範囲、販売停止、契約、顧客移行、返金、社内配置を自動変更しない。実行直前に対象顧客、契約条件、影響、代替案、移行日程を示し、利用者の明示承認を得る。
