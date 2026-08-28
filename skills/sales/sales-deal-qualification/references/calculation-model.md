# 計算モデル

- 加重金額 = 案件金額 × 利用者入力のステージ確率
- mustに `failed` があれば `disqualified`
- mustまたはadvancedゲートが `verified` でなければ `conditional`
- ゲートが揃い期限警告がなければ `continue`
- 失格なら `exit`、阻害要因があれば `hold`、高額かつ阻害要因があれば `founder_intervention`

期限超過や予測期間外は警告であり、入力確率を書き換えない。shouldの未確認は検証対象に残すが、must失格と同じ扱いにしない。

不明な金額・確率は該当案件の加重金額だけをnullにする。資格ゲートの結果は残す。`analysis_quality` は局所化した不明値と警告を示す。
