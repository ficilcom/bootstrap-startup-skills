# インテークと算定方法

## インテーク

質問より先に、次の資料の有無を確認する。無い資料は「無い」と記録し、推測で埋めない。

| 資料 | 取れる事実 |
| --- | --- |
| 返済予定表（金融機関別） | 残高、金利、残期間、据置期間、次回返済月、返済方式 |
| 借入金明細（勘定科目内訳明細書） | 借入先、残高、保証・担保の有無 |
| 決算書（直近期） | 税引後利益、減価償却費、営業キャッシュフロー |
| 試算表（直近月まで） | 期中の実績、季節性、直近の資金繰り |
| 信用保証の決定通知、担保設定の書類 | 保証区分、担保の種類、保証協会の関与 |
| 金銭消費貸借契約書の特約 | 財務制限条項、期限の利益喪失事由、繰上返済条件 |

`bank-loan-readiness` を既に実施している場合は、そこで作った資料台帳と返済予定をそのまま入力に使い、適格性ルーブリックを再実行しない。逆に、このスキルで算出した DSCR と債務償還年数は、`skills/finance/bank-loan-readiness/` の返済能力と借入妥当性の評価根拠として戻せる。全社の資金繰りを月次より細かく見る必要がある場合は `skills/finance/cash-runway-planner/` に、確定した返済額を流出として渡す。

収集しないもの: 個人の信用情報、金融機関の担当者名、口座番号、暗証情報、返済予定表の原本画像。

## 計算契約

入力は次の形の単一JSONファイルとし、スキル外に置く。金額と数値は `{"amount": …, "evidence": …}` / `{"value": …, "evidence": …}` の形で渡し、`evidence` は `confirmed`、`reported`、`estimated`、`unknown` のいずれかとする。`unknown` のときは値を `null` とし、0を入れない。

```json
{
  "as_of_date": "2026-08-22",
  "currency": "JPY",
  "horizon_months": 12,
  "cash_flow": {
    "period": {"start": "2025-09-01", "end": "2026-08-31"},
    "net_income_after_tax": {"amount": 4200000, "evidence": "confirmed"},
    "depreciation": {"amount": 1800000, "evidence": "confirmed"},
    "operating_cash_flow": {"amount": 5400000, "evidence": "reported"},
    "normalization_adjustments": [
      {"id": "one-off-grant", "label": "補助金入金", "direction": "subtract",
       "amount": {"amount": 1000000, "evidence": "confirmed"}}
    ]
  },
  "cash_position": {
    "available_cash": {"amount": 6000000, "evidence": "confirmed"},
    "minimum_cash_buffer": {"amount": 2000000, "evidence": "reported"},
    "monthly_net_cash_before_debt_service": [
      {"month": "2026-08", "amount": {"amount": 350000, "evidence": "reported"}}
    ]
  },
  "loans": [
    {
      "id": "jfc-2024",
      "label": "日本政策金融公庫 2024",
      "lender_type": "government_affiliated",
      "guarantee": "none",
      "collateral": "none",
      "outstanding_principal": {"amount": 9000000, "evidence": "confirmed"},
      "annual_interest_rate_percent": {"value": 1.8, "evidence": "confirmed"},
      "repayment_type": "equal_principal",
      "remaining_term_months": {"value": 48, "evidence": "confirmed"},
      "grace_remaining_months": {"value": 0, "evidence": "confirmed"},
      "first_payment_month": "2026-08",
      "covenants": [{"id": "net-assets", "label": "純資産維持", "type": "financial", "status": "met"}]
    }
  ],
  "proposed_borrowing": {
    "principal": {"amount": 5000000, "evidence": "reported"},
    "annual_interest_rate_percent": {"value": 2.1, "evidence": "estimated"},
    "term_months": {"value": 60, "evidence": "reported"},
    "grace_months": {"value": 6, "evidence": "reported"},
    "repayment_type": "equal_principal",
    "purpose": "working_capital",
    "drawdown_month": "2026-10",
    "first_payment_month": "2027-05"
  },
  "policy": {
    "dscr_floor": {"value": 1.2, "evidence": "reported"},
    "debt_repayment_years_ceiling": {"value": 10, "evidence": "reported"}
  },
  "downside": {"cash_flow_multiplier": {"value": 0.7, "evidence": "estimated"}}
}
```

列挙値: `lender_type` は `government_affiliated | bank | shinkin | credit_union | nonbank | other`、`guarantee` は `none | credit_guarantee_association | personal | other | unknown`、`collateral` は `none | real_estate | deposit | receivables | other | unknown`、`repayment_type` は `equal_principal | equal_installment | bullet | custom`、`covenants[].status` は `met | breached | unknown`、`purpose` は `working_capital | capex | refinance | other`。

`monthly_net_cash_before_debt_service` は基準日の月から `horizon_months` 分を連続して並べる。返済額は含めない。`proposed_borrowing` と `policy` と `downside` は任意。

`repayment_type` が `custom` の場合のみ `scheduled_payments` を渡す。`first_payment_month` から連続し、見通し期間を超えず、見通し末月と借入完済月の早い方までを覆う必要がある。

```json
"scheduled_payments": [
  {"month": "2026-09",
   "principal": {"amount": 187500, "evidence": "confirmed"},
   "interest": {"amount": 13500, "evidence": "confirmed"}}
]
```

### 算式

- 簡易キャッシュフロー = 税引後利益 + 減価償却費 + 加算調整 − 減算調整。`operating_cash_flow` を渡した場合は差分を併記するのみで、両者を平均しない。
- 返済予定表の再構築: `equal_principal` は据置期間中は利息のみ、以後は元金を残存回数で均等配分する。`equal_installment` は据置後の期間に対する元利均等額を用い、金利0のときは元金を回数で割る。`bullet` は毎月利息のみ、最終月に元金全額。`custom` は渡された金額をそのまま使う。
- 年間返済額は、見通しの先頭12か月分を合計する。見通しが12か月未満の場合は12か月換算し、換算した旨を出力に残す。
- DSCR = 簡易キャッシュフロー ÷ 年間返済額。年間返済額が0のとき、または借入の元本・金利・残期間が不明で返済予定を再構築できない借入があるとき、DSCR は算出せず理由を返す。
- 債務償還年数（総額）= 借入残高合計 ÷ 簡易キャッシュフロー。手元資金控除後 = （借入残高合計 − max(0, 手元資金 − 最低現金バッファ)）÷ 簡易キャッシュフロー。
- 追加借入余地は2つの制約を別々に計算する。返済余力制約は「簡易キャッシュフロー ÷ DSCR下限 − 既存の年間返済額」を年間返済額の上限とし、検討中の借入の金利と期間が分かるときだけ年金現価で元本に換算する。債務償還年数制約は「簡易キャッシュフロー × 上限年数 − 純有利子負債」を元本の上限とする。
- 下振れ倍率はキャッシュ創出にのみ乗じる。月次のネット資金が正の月にだけ適用し、既に流出の月と、期首の手元資金と、契約上確定している返済額には適用しない。

### 算出しない場合

- キャッシュフローの構成要素が `unknown` のとき、DSCR、債務償還年数、追加借入余地は `null` とする。返済予定表と年間返済額は借入条件だけで決まるため、そのまま出す。
- 手元資金または最低現金バッファが `unknown` のとき、手元資金控除後の償還年数とバッファ割れ月は `null` とする。
- 元本または金利が `unknown` の借入は年間返済額から除き、`missing_inputs` と `excluded_loan_ids` に記録する。このとき DSCR は部分集計で算出せず `null` とする。

## 判定と閾値

DSCR や債務償還年数に、業種や事業段階を越えて通用する合格ラインは存在しない。同じ数値でも、担保や信用保証がある借入、返済原資が安定している事業、設備投資の回収期間が長い事業では評価が変わる。したがって:

- `policy` に値が入っていない場合、出力の `policy_status` は `policy_not_set` となり、合否を判定しない。この状態で「基準を満たしている」と書かない。
- 基準は、利用者が自社の方針として決めた値か、金融機関が明示した値だけを入れる。一般論として流布している数値を基準として持ち込まない。
- 2つの制約が異なる答えを出すのが普通である。出力の `binding_constraint` は、どちらが先に効くかを示すだけで、もう一方を無視してよいという意味ではない。
- `restructuring_signals` は条件の充足状況を示す固定の判定であり、優先度付きの行動計画ではない。`high` が出ていても、それ単独で条件変更を選ぶ根拠にはならない。

## リスケ検討の順序

基準に届かない結果が出た場合、条件変更の検討に入る前に、次の順序で確認する。

1. **先に自力で解けるかを確認する。** 売掛金の回収サイトと滞留（`skills/finance/accounts-receivable-control/`）、削減可能な固定費（`skills/finance/expense-and-saas-audit/`）、在庫と前払いの圧縮、資産売却、支払サイトの見直し。これらで足りるなら、取引関係への影響を伴う条件変更を選ぶ理由がない。
2. **条件変更の種類と影響を分けて理解する。** 元金据置は月次の負担を下げるが総返済額と最終期限を後ろに動かす。期間延長は月次負担を下げるが金利負担が増える。借換えは他行との関係を変える。いずれも信用保証の扱い、今後の追加調達、取引金融機関との関係に影響する。どれを望むかを決める前に、影響の範囲を書き出す。
3. **必ず事前に相談する。** 金融機関への相談は、返済が滞る前に行う。独断で支払を止めたり減額したりしない。期限の利益喪失事由に該当すると、その後に取れる選択肢が大きく減る。
4. **専門家の確認が要る論点を分ける。** 税務上の取扱い、経営改善計画の要否、認定支援機関の関与、条件変更後の格付けへの影響は、税理士・認定支援機関に確認する。このスキルは判断材料を整えるだけで、専門的な判定を代替しない。

## 報告書形式

次の見出しで日本語の報告書を書く。数値には必ず基準日、対象期間、証拠状態を添える。

### 意思決定サマリー

現在の返済余力、拘束している制約、追加借入の可否についての結論を3行以内で示す。基準が示されていない場合は、その旨を明記する。

### 前提と資料

基準日、通貨、見通し月数、キャッシュフローの対象期間、使った資料、`confirmed` 以外の証拠状態で扱った項目。

### 返済予定と返済余力

年間返済額（元金・利息の内訳）、DSCR、下振れ時の DSCR、債務償還年数（総額・手元資金控除後）、それぞれの基準に対する状況。算出できなかった指標は、その理由とともに書く。

### 追加借入余地

返済余力制約と債務償還年数制約の両方、拘束している側、換算に使った金利と期間の前提。検討中の借入がある場合は、実行後の DSCR、償還年数、バッファ割れ月。

### 月次の資金繰り

基準ケースと下振れケースの最低残高月と金額、バッファ割れ月。据置が明ける月と、その月から増える返済額。

### 注意すべき条件

`restructuring_signals` の内容を、深刻度と対象借入を添えて列挙する。条件変更を推奨しない旨を明記する。

### 不明点と次に集める根拠

`missing_inputs` に挙がった項目、それが結論のどこを変えうるか、誰にどの資料を求めるか。金融機関と話す前に用意すべき資料と論点。
