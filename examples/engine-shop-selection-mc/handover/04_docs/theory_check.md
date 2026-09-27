# 理論と実装の突き合わせ（theory_check）

2026-09-27。対象：`track.py` / `cpd.py` / `ooda.py` / `roll.py` / `build_report.py` / `report_hub_template.html` / README / note 草稿と、`handover/02_results/` の生成結果。数字はすべて合成データ。判定は PASS / PARTIAL / FAIL、根拠は file:line か生成 JSON の値。

集計：PASS 8（1,5,8,9,10,11,12,15）、PARTIAL 7（3,4,7,13,14,16,17）、FAIL 2（2,6）。17 項目。

## PDCA

**1. 三つの Check を別区画で見せる — PASS**
`report_hub_template.html:864-868` `loops()`：① 実行のずれ（計画 vs 実績）、② 前提のずれ（確率の更新と変化点）、③ 決め方のずれ（採点）を `box()` 三つに分け、`panel("確かめる：3 つのずれを分けて見る", checks)`（:886）で一区画にまとめる。

**2. 尤度のテンパリング γ=0.5、1 か月で先頭の世界がひっくり返らない — FAIL（後半）**
`track.py:159` `TEMPER = 0.5`、`:325` `prior × exp(TEMPER·(ll−max))`。しかし月 1 の事後確率（`timeline[0].posterior`）：
- jal-track-crunch：crunch 0.652、stress 0.345、base 0.002 → 1 か月で先頭が base → crunch に反転
- ana-track-crunch：crunch 0.512、stress 0.310、base 0.119 → 同じく反転
- 混雑側（jal/ana backlog）は base 0.667 / backlog 0.333 で反転せず。
理由：`kit_lead` の尤度（FLOOR 1.5 を √min(4,n) で割る、`:198`）が逼迫世界で強すぎる。README:337 は「ベイズは月 1 で動く」と正直に書いているが、「1 か月で確定させない」という設計意図（`:157-158` コメント）と矛盾。直し方：kit_lead の FLOOR を上げるか、γ を月 1 だけ小さくする／事前分布を反映して「動いた」判定を 2 か月連続にする。

**3. 乗り換えルール：ΔV から緊急キット割増を引く、履歴 2 か月 — PARTIAL**
- 割増の控除：`track.py:381` `"saving": keep − a["mean"] − late × probs[w].emergency_kit_premium`（枠の予約遅れは追加費用なしと仮定、`:378-379`）。枠予約の切替コストそのものは引いていない。
- 履歴：`track.py:445` `hysteresis_ok = best_now > MATERIAL_K and best_prev > MATERIAL_K`（`MATERIAL_K = 300`、`:160`）＝当月と前月の 2 か月連続。`build_report.py:98` が推奨判定に使う。ただし候補別ではなく「最良候補の ΔV」で判定するので、候補が入れ替わっても通る。`ooda.py:105` の world_shift ルールは履歴を見ず、事後確率 >0.5 だけで毎月会議へ（ana crunch で 12 か月連続 12 件）。
- 生成結果：ana-track-crunch `hysteresis_ok` は k=2〜11 True（ΔV 981→1,134 k$）、jal-track-crunch は k=9〜11 のみ True。
- テスト：`tests/test_theory.py` `SwitchRuleTest` は同じ式をテスト内ヘルパーに写して ±ΔV 列を検証（[500,500,−100,400,350,250,400] → [F,T,F,F,T,F,F]）。**track.py 自身は関数を公開していない**（status() の中にインライン）→ PARTIAL。直し方：`switch_saving()` と `hysteresis_ok()` を track.py の関数に切り出す。

**4. roll の Z=n/(n+12)、変化点でリセット — PARTIAL（機構 PASS、「真値に近づく」は FAIL）**
- `roll.py:36` `K0 = {"delay": 12, "findings": 12, "unsched": 12, "hazard": 8}`、`:39-40` `cred = n/(n+k0)`。
- リセット：`:54-56` 変化点が backlog 側なら `reset_at = cpd_month − 1` 以降に入場した機の戻りだけを使う。
- 真値：backlog 世界は見積もり TAT +1 か月。モデル自身の期待超過（`timeline[-1].expected`）は base 1.19 / backlog 2.18（JAL）、1.14 / 2.14（ANA）。
- 生成値（`learned.delay`）：
  - JAL：リセットあり n=11 観測 1.091 → 更新 **1.122**、なし n=16 観測 1.125 → 更新 **1.136**（事前 1.15）
  - ANA：あり n=5 観測 1.00 → **1.106**、なし n=9 観測 1.00 → **1.086**
- 判定：真値 2.18 / 2.14 に対し、JAL はリセットありの方が**遠い**、ANA は僅かに近いが観測値は同じ 1.00 で重みの差だけ。そもそも合成実績の戻り超過は全件 1〜2 か月（平均 1.0〜1.1）で base の期待値と一致し、backlog の +1 が実績に出ていない（`make_actuals` は真の世界を t=0 から全機に適用しているので、変化前の観測を落とす理由も合成データ上は無い）。README:342 の「効果は小さいが筋は通る」は数字の裏付けがない。直し方：合成実績の生成で TAT の +1 を `change_week` 以降の入場に限定し、再検証する。

**5. 橋渡しの恒等式 — PASS**
`jal-roll-2027-10.json`：165,462 + 29,902 + 7,179 + 0 = 202,543（差 0）。`ana-roll-2027-10.json`：109,915 + 47,750 − 15,059 + 0 = 142,606（差 0）。「決め方を変えた分（γ・K・世界の集合は今回変えていない）」= 0.0 が両社にある（`roll.py:233`）。`tests/test_theory.py` `BridgeIdentityTest` で固定。

**6. タイミング D + A ≤ R を判断ごとに評価 — FAIL**
- `ooda.py:162` の `timing_rule` は固定文字列、`R_months` はキット納期（8 か月）一つだけ。判断ごとの D+A≤R の評価はどこにもない。判断期限そのものは `track.py:178-186` `hybrid()` が変更ごとに `decide_t` / `overdue` を出しており、これが per-decision の材料だが、D と A は結び付けていない。
- 文字列中の「1 か月遅れるごとに約 0.9 百万ドル」および README:281 の「すぐ乗り換えれば約 140 万ドル、1 か月遅れると約 50 万ドル」は生成結果で再現しない：
  - ana-track-crunch `cpd.value`：at_cpd **+981** k$、at_bayes +408、one_month_late **+1,032**（遅れた方が高い）、worth 573
  - jal-track-crunch：at_cpd **−1,842**、one_month_late **−1,842**、worth 0（月 8 から +914）
- また `handover/02_results/*-track-*.json` には `delay_curve` が無い（`track.py:238-241` の追加より前に生成）。`build_report.py:123` は `v.get` で耐えるが、レポートの「遅れの費用」図は空になる。
- 直し方：README:281 と `timing_rule` の数字を削るか生成値に差し替え、track JSON を再生成。D+A≤R は `hybrid()` の `decide_t` に対して `k + A ≤ decide_t` を変更ごとに出す。

## OODA

**7. 会社別 rules.json、単位価値 v — PARTIAL**
`data/jal/rules.json`、`data/ana/rules.json` は**存在しない**。`ooda.py:41-45` `load_rules` が `DEFAULT_RULES` に落ちる（テスト `test_rules_json_missing_falls_back_to_defaults` で確認）。README:356「`data/<company>/rules.json`」の記述は現状と一致しない。v は `ooda.py:48-52` = 年間整備費 ÷（保有 − 棚の予備）÷ 12。生成値 `ooda.unit_value_k`：JAL **116.0** k$、ANA **95.9** k$。

**8. ルールが合成事象で発火し会議を迂回 — PASS**
`ooda.feedback.rule_cases_by_rule`：jal crunch teardown_extra 6・cm_alert 3（計 9 件をルールで決定、world_shift 12 件は会議へ）、ana crunch 4・2（計 6、会議 12）。`teardown_review` は両社「承認線 v を見直す」（純額 JAL 6,897 k$、ANA 1,036 k$）。tat_slip は ana backlog で 1 件出たが安全スイッチ下で会議へ。

**9. 安全スイッチ — PASS**
`ooda.py:67-68` state==cpd_only で `safety_from = cpd_month`、`:73` 月ごとに再判定、`:135-137` `_case` が safety 時に `to_meeting=True`・判断「会議へ（安全スイッチ）」。生成：jal/ana backlog は k=2〜12 の 11 か月 safety、全 20 / 18 件が会議へ、`rule_cases` 0。テスト `SafetySwitchTest`：どの世界にもない衝撃（見積もり TAT +12 週）で `cpd.detect_streams` が月 3 に発火、事後確率は動かず `change_points` が cpd_only、`replay` で全件が会議へ・`rule_cases`=0・`add_world`=True。変化点なしなら同じ案件をルールが決める（対照テスト）。

**10. ループ時間の部分と前後 — PASS**
`ooda.py:146-163`：D/O/A/E に `now` / `was` / `target`。生成（backlog）：D now 2.0、was 「12+（前提の確率が動かず）」；crunch：D now 2、was 1（ベイズが先）。T_now 12.0 → T_target 5.35。備考：D の「now」は cpd_month（絶対月）で、変化点（週 6）からの遅れではない。

**11. OODA→PDCA の受け渡し — PASS**
`track.py:448` `ooda.replay` → `out["ooda"]`；`roll.py:196` `TJ["ooda"]["feedback"]` → `learn(... ooda_fb)` → `evidence.ooda`。`*-roll-2027-10.json` `learned.ooda` に `rule_cases`、`no_world_fits_months` 11、`add_world` true、`actions` 4 件。

## CPD

**12. uer_arl — PASS（数値は弱いと正直に書いてある）**
生成 `cpd.uer_arl`（λ0=0.5/月、+20%、300 回）：CUSUM mean_delay 9.92、false 0.047、p_detect_12m 0.127、missed 0.74；MA3 8.08、0.037、0.037、missed 0.92。README:341 の 13% / 4%、5% / 4% と一致。mean_delay は検出できた回だけの平均なので MA3 の方が短く見える点に注意。

**13. 不一致警報の両方向 — PARTIAL**
`track.py:272-277` に cpd_only / bayes_only の verdict 文字列あり。月別 state では jal/ana crunch の k=1 に `bayes_only` が出る（キット納期回答で先にベイズが動く）が、最終 verdict としての bayes_only は合成データでは一度も出ていない（最終 state は backlog=cpd_only、crunch=both）。

## 節約の集計

**14. — PARTIAL（既知の所見を再掲し、合計を訂正）**
- 中寿命（グリーンタイム 8 基）：`*-deltas.json` の答え「グリーンタイム・エンジンを最大 8 基使えたら」の delta.total_cost = **−36,994 k$ JAL / −37,780 k$ ANA**（2 年計画、`actions.py:103` の GT 価格 5,000 k$ 込み）→ 年 ≈ 18.5 / 18.9 百万ドル。「年 ≈5 百万ドル」は README の単一フリート例で、会社別の生成値ではない。
- 乗り換え：ANA crunch at_cpd **+1.0 百万ドル**（一回限り、逼迫世界のみ）、JAL 0（月 8 まで損）。
- 共同の枠確保：`invest.json booking.pv_cfm56` = **4.60 百万ドル**（PV、2026〜30 の 5 年）→ ≈ JAL 0.6 / ANA 0.3 百万ドル/年（配分は以前の所見どおり）。
- CPD の価値：`cpd.value.worth` JAL 0、ANA crunch **0.57 百万ドル**（上の +1.0 に含まれる差分。二重計上しない）。
- 訂正後の合計（合成データ）：JAL ≈ 18.5 + 0.6 ≈ **19 百万ドル/年**、ANA ≈ 18.9 + 0.3 ≈ **19 百万ドル/年** ＋ 逼迫が実際に来た年だけ +1.0（うち CPD 分 0.57）。1 年目の立ち上がり（ramp）はデータから導けない（前提として置くしかない）。

## 衛生

**15. テスト — PASS（既存 1 件の失敗は別件）**
`tests/` は作業前から存在（`test_shop_mc.py`）。`python -m unittest discover -s tests -v` → `Ran 18 tests in 7.104s` / `FAILED (errors=1)`。失敗は既存の `test_shop_mc.ShopMcTest.test_fixed_price_shop_never_bills_overrun`（`tests/test_shop_mc.py:55` `StopIteration`：OEM-NET の PR オプションが現在の `data/shop_quotes.json` に無い）。単独実行でも同じ。新規 `tests/test_theory.py` は 10 件 `OK`（0.11 s）。

**16. 合成データの注記 — PARTIAL**
`report_hub_template.html:153`（冒頭 hint）、:596、:662 に「合成データ」。note 草稿 `note_draft.md:25` に冒頭注記（引用ブロック）。Slides はリポジトリ外で確認不可。

**17. note 草稿の語句 — PARTIAL**
「年 20〜30」なし、「年 10〜30」あり（`note_draft.md:29`）。「メタ」は本文にはないが、引き継ぎヘッダー（:5, :7, :13）に依頼原文と禁止ルールの引用として残る。投稿時にヘッダーを落とす前提なら問題ないが、機械的に grep すると引っかかる。加えて :59「6 か月目に検知」は生成値（CPD 月 2、ベイズは動かず）と合わない（README:281 と同じ旧記述）。

## 直すべき順

1. README:281 と `ooda.py:162` の「140 万 / 50 万 / 0.9 百万ドル/月」を生成値に合わせる（項目 6）。track JSON を再生成して `delay_curve` を入れる。
2. 逼迫世界で月 1 に反転する尤度（項目 2）：kit_lead の FLOOR か γ の扱い。
3. 合成実績の TAT +1 を変化週以降に限定し、リセットの効果を測り直す（項目 4）。
4. `data/<co>/rules.json` を置くか README の記述を DEFAULT_RULES に直す（項目 7）。
5. 乗り換えの式と履歴判定を track.py の関数に出す（項目 3）。
