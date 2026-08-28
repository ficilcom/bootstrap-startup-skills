---
name: vendor-selection-review
description: Compare software, service, and outsourcing vendors using lifecycle cost, requirement evidence, usage scenarios, contract and exit gates, fit, and reliability. Use before selecting, renewing, or replacing a vendor; do not use as authorization to sign, purchase, migrate, or cancel.
license: MIT
metadata:
  author: ficilcom
---

# ベンダー選定レビュー

価格表だけでなく、導入・移行・運用・退出までの総コストと、適合性、信頼性、セキュリティ、ロックイン、契約条件を同じ期間で比較する。

## 進め方

1. [インテークと比較方法](references/intake-and-method.md)を読み、必須要件、利用量、既存環境、移行期限、契約・データ退出条件を確認する。
2. 同じ通貨、税、比較期間、利用量シナリオへ揃え、値引き終了後の価格も含める。金額と工数を `confirmed`、`reported`、`estimated`、`unknown` に分ける。必須要件、更新後価格、追加費用、候補別シナリオまで比較する場合は `advanced` を選び、[要件と契約](references/requirements-and-contracts.md)を読む。
3. [計算モデル](references/calculation-model.md)に従い匿名化JSONを作り、スキルのルートで `python3 scripts/compare_vendors.py <input.json>` を実行する。
4. core TCO、advanced TCO、シナリオ別TCO、要件ゲート、信頼性、セキュリティ、ロックイン、契約、退出可能性を別々に比較する。最低価格や自己申告だけで選定しない。
5. [報告書形式](references/report-format.md)で候補、失格条件、確認事項、交渉条件、小規模検証、切替・撤退条件を示す。

## 判断上の制約

- 初年度割引、無料移行、従量超過、最低契約、解約通知、データ出力、サポートを含める。
- ベンダーの自己申告と検証済み証拠を分ける。法務・セキュリティ・個人情報の判断は適切な専門レビューへ渡す。
- 機能数ではなく必須業務への適合で評価する。不明コストをゼロにせず、比較順位から除外する。

## 権限境界

購入、契約、更新、解約、データ移行、権限付与、外部連絡を自動実行しない。対象、金額、契約期間、データ影響、移行・撤退条件について利用者の明示承認を得る。
