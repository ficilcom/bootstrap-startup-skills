---
name: security-questionnaire-readiness
description: Assess readiness for a customer security questionnaire or information-management review by inventorying each item's current state and supporting evidence, counting only evidence-backed items as answerable, listing the must-level gaps that block the deal, and back-scheduling remediation against the submission deadline and available hours. Use when a prospect or existing customer sends a security check sheet and the response is blocking a deal; do not use it to certify compliance, to determine whether a control satisfies a standard or regulation, to answer or submit the questionnaire, or to represent an unimplemented control as implemented.
license: MIT
metadata:
  author: ficilcom
---

# セキュリティ質問票対応準備

取引先のセキュリティチェックシートに対し、設問ごとの現状と証跡を棚卸しし、証跡付きで回答できる件数、案件を止める必須ギャップ、提出期限から逆算した是正計画を示す。準拠の認定ではなく、質問票への回答代行でもない。

## 進め方

1. 最初に [インテークと方法](references/intake-and-method.md) を読み、質問票、提出期限、対象案件、設問ごとの現状と証跡、割ける週あたり時間を確認する。個人名、顧客名、認証情報、ホスト名を入力へ含めない。
2. [典型カテゴリと必要な証跡](references/question-categories.md) に沿って設問をカテゴリへ寄せ、各設問に求められる証跡の型を確定する。規程だけで足りるのか、実施記録が要るのかを分ける。
3. 現状を `implemented`、`partial`、`not_implemented`、`unknown` に分け、証跡を `document`、`configuration`、`log`、`third_party`、`none`、`unknown` に分ける。工数が読めない設問はゼロではなく `unknown` にする。
4. [計算モデル](references/calculation-model.md) に従いスキル外へ匿名化JSONを作り、スキルのルートで `python3 scripts/assess_security_readiness.py <input.json>` を実行する。費用と代替統制を見る場合は `analysis_mode` を `advanced` にする。
5. 必須ギャップと期限超過の起点を確認する。期限内に収まらない場合は、是正を絞る、期限延長を相談する、未実装のまま実装予定時期を添えて回答する、の3つを分けて比較する。
6. [報告書形式](references/report-format.md) で、カバレッジ、必須ギャップ、是正スケジュール、代替統制、選択肢を示す。各是正に担当と完了条件を置く。

## 判断上の制約

- 証跡のない統制を回答可能として数えない。`partial` を `implemented` へ丸めない。
- クラウド事業者側の統制を自社の統制として計上しない。責任分界を確認したうえで分ける。
- 受入が未確認の代替統制で必須ギャップを消さない。取引先が受け入れた場合だけ充足として扱う。
- 設問が規格や法令の要求を満たすかを判定しない。判断が必要なら該当分野の専門家と取引先の確認条件を示す。

## 権限境界

質問票の回答作成、送信、取引先への申告、設定変更、ツール導入、規程の発行と改訂、委託先への連絡を自動実行しない。未実装の項目を実装済みとして記載する回答案を作らない。実行直前に対象、記載内容、根拠となる証跡、影響を示して利用者の明示承認を得る。このスキルの利用承認は外部行為の承認ではない。
