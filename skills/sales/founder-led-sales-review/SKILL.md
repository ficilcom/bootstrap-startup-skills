---
name: founder-led-sales-review
description: Diagnose where founder-led sales are stalling by normalizing pipeline stages, measuring aligned conversion, velocity, ageing, and loss reasons, then prioritizing the founder's next sales actions. Use when reviewing a B2B or service sales pipeline, weekly sales progress, or a suspected funnel bottleneck; do not use for CRM administration, automated outreach, or forecasting booked revenue without reliable opportunity data.
license: MIT
metadata:
  author: ficilcom
---

# 創業者主導営業レビュー

創業者が担う販売活動について、案件の量だけでなく、どのステージで転換・進行速度・滞留が悪化しているかを特定し、次の一手を具体化する。これは営業運営の診断であり、将来受注や売上を保証する予測、顧客価値の判定、CRMの更新代行ではない。

## 進め方

1. 最初に [インテークとレビュー方法](references/intake-and-method.md) を読み、利用者が渡したCRM出力、商談メモ、メール・通話の集計、失注記録を質問より先に確認する。不要な顧客連絡先、認証情報、会話全文は収集しない。
2. 目的（例: 今月の受注、発見面談の質、特定セグメントの検証）、基準日、分析期間、コホート、対象セグメント、ステージ定義を一つに固定する。資料間の名称や完了条件が違う場合は、原データを上書きせず正規化対応表を作る。
3. 重要な事実と仮定を `confirmed`、`reported`、`estimated`、`unknown` に区別する。`unknown` を失注、ゼロ件、または平均日数に置き換えない。失注・放置・保留も別の状態として扱う。
4. 機械可読な履歴がある場合は、[計算契約](references/intake-and-method.md#計算契約) に従い、必要最小限に匿名化したJSONをスキル外へ置き、スキルのルートで `python3 scripts/analyze_pipeline.py <input.json>` を実行する。出力は診断材料であり、CRMの変更を行わない。
5. [診断と優先順位](references/intake-and-method.md#診断と優先順位) を使い、母数、転換率、ステージ通過日数、滞留、失注理由、パイプラインのカバレッジを同じ期間・コホートの範囲で比較する。指標の母数や観測期間が異なるなら、単一のランキングに混ぜず比較不能と表示する。
6. [報告書形式](references/intake-and-method.md#報告書形式) に従い、最優先のボトルネック、根拠、不確実性、創業者が次に行う少数のアクションを示す。各アクションには対象、目的、期限、成功・停止判定、必要な入力を置く。

## 判断上の制約

- ステージの件数だけで「健全」と結論づけない。転換率には分子・分母・コホート、速度には開始・終了イベントと時間単位を必ず添える。
- 小さい母数では率を精密な比較や一般化に使わない。件数を併記し、1件の増減で結論が変わる場合は検証優先度として扱う。
- 失注理由は空欄を勝手に補わず、理由不明を独立集計する。営業担当の推測と顧客が明示した理由を区別する。
- 創業者の次のアクションは、ボトルネックを最も減らせる仮説検証または既存案件の前進に結び付ける。一般的な「フォローアップを増やす」を、対象・次の相互行為・判断期限なしに推奨しない。

## 権限境界

このスキルは、分析、行動案、送信前の文面案、CRM更新案を作るだけである。外部CRMの更新、商談作成、顧客・見込み客への連絡、価格・契約条件の提示、カレンダー招待、広告変更を自動実行しない。実行直前に、対象、内容、時期、担当、影響を示して利用者の明示的な承認を得る。このスキルの利用承認は、それらの外部行為の承認ではない。
