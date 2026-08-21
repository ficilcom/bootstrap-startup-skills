---
name: pricing-decision
description: Compare price increases, plan and packaging changes, pricing metrics, and discount policies; quantify revenue, contribution, customer migration, and guardrail impact; and design a validation plan for recurring, transactional, or service-project businesses. Use when deciding whether and how to change pricing; do not use for securities pricing, statutory transfer pricing, pricing-page copy alone, or automatic live price changes.
license: MIT
metadata:
  author: ficilcom
---

# 価格変更の意思決定

値上げ、プラン再編、課金単位、割引・契約期間の案を比較し、売上・限界利益・顧客移行・キャパへの影響と検証方法を示す。対象は継続課金、取引、サービス案件のいずれか一つであり、価格変更の実行、証券価格、法定移転価格、価格ページ文言だけの改善ではない。

## 進め方

1. 最初に [インテーク](references/intake.md) を読み、提出済みの料金表、請求、利用量、契約、更新、解約、失注、値引き、原価資料を質問より先に確認する。重要入力を `confirmed`、`reported`、`estimated`、`unknown` に分け、`unknown` をゼロにしない。
2. 1回の分析につき一つの業態モード、収益ストリーム、通貨、期間、使用量・キャパ単位を定義する。顧客は匿名の相互排他的なセグメントに集約し、個人情報や保護属性を価格区分に使わない。
3. [価格案設計](references/proposal-design.md) を読み、利用者の主目的と明示的なガードレールを決める。価格額、プラン構成、課金単位、割引・契約期間から、意思決定上異なる少数の案を作る。
4. [移行方針](references/migration-policy.md) を読み、各セグメントに `immediate`、`renewal`、`delayed`、`grandfathered`、`phased`、`manual_review` のいずれかと、判断期間内の移行割合を割り当てる。
5. [計算モデル](references/calculation-model.md) を読み、必要最小限に匿名化したJSONをスキル外へ作る。スキルのルートで `python3 scripts/calculate_pricing_decision.py <input.json>` を実行する。
6. 検証エラーは入力を訂正する。価格感応度、継続率、新規顧客、利用量を推測で埋めない。不明な重要反応は `hold_for_evidence` として残す。
7. 出力の目的差、ガードレール、価格負担、移行対象、感度を確認する。[検証計画](references/validation-plan.md) を読み、結論を左右する不確実性に対する最小の検証を設計する。
8. [報告書形式](references/report-format.md) を読み、利用者の言語で報告する。判断期間後のランレート、一時費用、累積キャッシュ効果を分ける。

## 判断上の制約

- 利用者が主目的を選ばない場合、売上最大化を仮定せず、価格案を好意的に決定しない。
- 解約、転換率、使用量、顧客獲得、支払意思を、競合価格や原価だけから推定しない。
- 普遍的な値上げ率、解約率、利益率、転換率の合格基準を置かない。利用者が示したガードレールだけを合否判定に使う。
- `candidate_for_rollout` は仮定と証拠の範囲内の判定であり、需要、キャッシュ、法的有効性、顧客受容を保証しない。
- 一時導入費をランレート利益へ混ぜず、判断期間末の改善を期間全体の実現キャッシュとして掛け算しない。
- 顧客別の恣意的価格ではなく、契約時期、利用量、プラン、採算、関係リスクなど説明可能な集計セグメントで移行方針を作る。

## 最新情報と権限

契約通知、消費者保護、競争法、規制価格、税務など現在の制度事実が判断を左右する場合だけ、当日の権威ある一次情報または適切な専門家へ確認する。この診断を法務、税務、会計上の専門判断として扱わない。

価格公開、価格ページ変更、請求設定、契約・更新条件、顧客連絡、広告、実験、送金、取引を実行する直前に、利用者の明示承認を得る。このスキルの利用承認は外部行為の承認ではない。
