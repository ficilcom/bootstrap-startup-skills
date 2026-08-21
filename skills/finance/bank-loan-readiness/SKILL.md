---
name: bank-loan-readiness
description: Assess how ready a Japan-based founder or small business is to apply for a business loan, using available plans and financial documents plus focused follow-up questions. Use for pre-application diagnosis, weakness identification, and improvement planning for startup or operating-company borrowing; do not use the score as an approval prediction.
license: MIT
metadata:
  author: ficilcom
---

# 融資申請準備度診断

日本に関係する創業者・中小事業者について、融資申請前の準備度、根拠の不足、優先改善事項を診断する。スコアは申請準備の度合いであり、承認確率、金融機関の内部判断、または専門家の判断ではない。すべての重要情報を `confirmed`、`reported`、`inferred`、`unknown` に区別し、未確認を不利な事実として扱わない。

日本以外の法域を主対象とする案件は、このスキルだけで結論を出さない。対象法域と専門家による確認が必要な点を明示する。

## 進め方

1. まず [資料起点インテーク](references/intake.md) を読み、日本との関係、対象範囲、利用可能な資料、事業開始日、完了決算期の有無を確認してモードを決める。
   - `startup`: 開業前、または最初の決算期を完了していない。
   - `operating_company`: 少なくとも1期分の決算を完了している。
   - モードを選べなければ、事業開始日と完了決算期の有無だけを質問し、採点を保留する。
2. 提出済みの資料を先に読み、資料台帳と重要な不整合を作る。資料で確認できることは再質問せず、評点・情報区分・赤旗判定・融資ルート・推奨行動を変え得る事項だけを追加で確認する。不要な口座番号、個人番号、本人確認書類番号、詳細な信用情報は収集・複製しない。
3. 選択したモードのルーブリックだけと [赤旗](references/red-flags.md) を読む。
   - `startup` は [スタートアップ・ルーブリック](references/startup-rubric.md)。
   - `operating_company` は [事業継続会社ルーブリック](references/operating-company-rubric.md)。
   - 選択していないモードのルーブリックは読まない。
4. 選択モードの全評価項目を正規化する。各項目に `rating`（0–5 の整数）、`evidence`、短い根拠、評価理由を残す。`unknown` は不明な理由と確認質問を残し、低評点や赤旗に置き換えない。確認済みまたは本人申告済みの重大懸念だけを赤旗候補にし、`inferred` と `unknown` の懸念は未解決事項に残す。
5. スコアラー用には、スキルのディレクトリ外に、必要最小限の匿名化した JSON ファイルを作る。全評価項目の `rating` と `evidence`、および該当する `confirmed` / `reported` 赤旗だけを含める。

   ```json
   {
     "mode": "startup",
     "criteria": {
       "criterion_name": {"rating": 0, "evidence": "unknown"}
     },
     "red_flags": [
       {"code": "flag_code", "severity": "major", "evidence": "confirmed"}
     ]
   }
   ```

   評価項目は選択モードで期待されるキーを過不足なく入れる。赤旗のコード、重大度、許可される根拠区分は [赤旗](references/red-flags.md) に従う。
6. スキルのルートで `python3 scripts/calculate_score.py <input.json>` を実行する。検証エラーが出たら、推測で補完せず入力を修正してから続ける。出力の `raw_score`、`final_score`、`readiness_band`、`confidence_percent`、`provisional`、`criterion_points`、`missing_core_criteria`、`applied_cap` を保持する。
7. [融資ルート](references/lending-routes.md) と [報告書形式](references/report-format.md) を読み、所定の見出し順で日本語の報告書を作成する。スコア、各項目の根拠・情報区分・理由、確認済み赤旗、未解決事項、資料不足、優先改善行動、適合傾向を分けて示す。`provisional` が真なら、スコアの近くに「暫定」と不足理由を明示する。

## 最新情報と権限

具体的な制度、現在の条件、金利、限度額、地域・業種の取扱いを求められた場合だけ、その日の公式情報を調べ、確認日と出典を報告する。制度の案内や適合傾向を、利用可否や承認の断定にしない。

申込み、提出、金融機関その他への連絡、信用情報の取得など、外部への行為は利用者の明示的な承認を得てから行う。
