# 引き渡し一式（航空機エンジン整備計画・合成データ）

**すべて合成データです。** 公開情報からの推定で、特定の航空会社の実際の数値ではありません。
出典のない数字は `01_inputs/companies.json` と `01_inputs/leap_invest.json` の中で `no_source` / 確度 C と明記しています。

## 01_inputs — 入力（前提）
| ファイル | 中身 |
|---|---|
| companies.json | 会社ごとの前提：機数、エンジン数、契約工場、使われ方（運航部門ごとの飛行回数・区間・気候）、傷み方、値ごとの出典 |
| leap_invest.json | 国内工場（LEAP-1B）投資の前提：段階、費用、需要、交渉、3 社連合、受託市場、枠の取り合い（確度 A/B/C 付き） |
| shop_quotes.json | 5 工場の見積もり（契約更新時の入札ユースケース用） |
| jal/ana/fleet.json | 今後 24 か月に期限が来るエンジン、必要装着数、予備、予算など |
| jal/ana/shops.json | 契約工場（1 社） |
| jal/ana/actuals_*.json | 合成の実績（工場の混雑／部品不足の世界で基準計画を実行したもの）：入場、戻りと請求、予定外、キット納期回答 |

## 02_results — 計算結果
| ファイル | 中身 |
|---|---|
| *-2026-10.json | 基準の計画（版）：計画の各エンジン、月別（余力・平年値・工場の混み具合）、10 年見通し、前提ごとの計画案 4 つ |
| *-deltas.json | 打ち手・状況ごとの、基準からの増減 |
| invest.json | 国内工場の投資：案ごとの正味現在価値、損益分岐、内訳（交渉・足元）、3 社の取り分、受託市場の均衡、枠の取り合い |
| *-history.json | 過去の版（2 年前・1 年前）の当たり外れと計画の積み上がり |
| *-roll-2027-10.json | 次の版への引き継ぎ：実績で直した前提、固定した入場、前の版からの橋渡し |

## 03_reports — 画面（HTML、ブラウザで開く。外部通信なし）
| ファイル | 中身 |
|---|---|
| report.html | 経営レポート：結論 → ユースケース → 明細 → 前提と出典。見方の切り替え、各図に読み方 |
| monthly.html | 月次レポート：月を選ぶと月末時点の報告（着地の幅つき） |
| annual.html | 月次・年間計画（24 か月の帯、季節の平年値との比較） |
| track.html | 計画の追跡（時点スライダー、前提の確率、乗り換えの損得） |

## 04_docs — 文書
| ファイル | 中身 |
|---|---|
| README.md | 全体の説明と実行方法 |
| REQUIREMENTS.md | 要望の一覧（59 件）と対応状況、見本と実務の距離 |
| PRACTICE.md | 実務との照合（出典付き） |
| PROCESS.md | 業務プロセス（P1〜P11）と道具の対応 |

コード一式：リポジトリ `working-with-agi/sdk`、ブランチ `claude/aircraft-engine-repair-optimization-8oww5m`、`examples/engine-shop-selection-mc/`

（この repo 内のコピーでは 03_reports の HTML は省いています。各画面は `build_report.py` などで再生成できます）

## 数字の出どころ（patent 側の質問への回答、2026-09-27）

1. **予算を超える確率 60%**：`02_results/jal-track-backlog.json` → `timeline[k].forecast["FY2027"].p_over`。世界を確率で引き、各世界のシナリオから未請求分を 2,000 回合算した分布で予算超えの割合。JAL FY2027 は 0.59〜0.62 で推移。
2. **80% 点（予備費）**：同 `forecast[FY].p80` と `contingency_p80`（= p80 − 予算）。JAL FY2027：p80 186.4、予備費 20.8 M$。ANA FY2027：p80 133.1、予備費 37.6 M$。
3. **月ごとの差分**：`build_monthly.py` の `month_reports()` が `timeline[k]` と `[k−1]` の差（前提の確率、着地 p50、新しい例外）を計算。JSON には無く、レポート生成時に作る。
4. **「6 か月目に検知したが乗り換えないほうが得」**：単一フリート例（README の旧節）の数字。会社別は `timeline[k].switch[候補].saving / decide_by` と `cpd` ブロック。JAL 混雑：先行指標は月 2 で検知、前提の確率は月 5、乗り換えはどの月でも損。
5. **つながり 50% → 63%**：`build_report.py` の `horizons()`。矢印ごとに ok/warn/bad を判定し、score = ok 数 ÷ 矢印数。50% は追跡→次の版の矢印が未実装だった時点、63% は roll.py 実装後。
6. **出典のない数字 11 件**：`build_report.unsourced()` が companies.json の当該会社＋common の `no_source` を数える（当時 JAL 11、ANA 10）。その後、追加機種・契約形態・お金の仕組みの前提が増え、2026-09-27 時点では JAL 36 件。leap_invest・finance・tax・mx4・lease の各パラメータ表の no_source は別集計。
7. **グリーンタイム・エンジン（8 基）の −37.0／−37.8 M$**：購入価格 5,000 k$ を**差し引いた後**（`actions.py` の GT 価格、残存価値は CORE 相当で評価）。売り込みの上限額は「差額がゼロになる価格」で、会社別の感度は未計算。
8. **history の半期と通年の予算**：`fiscal_years` は実績のある月だけ集計（`months` に月数）。予算は通年の値なので、半期の行は `months` で按分する。

追加の出どころ：立て直し費の分離は `02_results/{co}-2026-10.json` の `candidates[*].summary.committed / recourse / recourse_p90 / recourse_parts`、打ち手の保険料・払い戻しは `{co}-deltas.json` の `delta.premium / payout`、お金の仕組みは `finance.py`（式）と `deltas` の `fin_*`（シミュレーション）、リース返却は `lease.py`、税引後は `tax.py`（追加中）。
