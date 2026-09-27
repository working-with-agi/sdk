# 実務との照合（公開情報、2026-09 時点）

このサンプルの前提を、公開情報で点検した記録です。数字の横に出典を付けています。有料記事や本文を読めなかった資料は「未確認」、公開の根拠が見つからない前提は「出典なし」と明記します。個社の内部の実務は公開されていないため、ここでの「実務」は業界で一般的な形と、各社の公表内容に限ります。

## 1. 構造がずれている前提（数字より先に直すもの）

| 前提 | 実務（出典） | 直し方 |
|---|---|---|
| 76 機・166 基を「グループ全体」で 1 つの計画にする | JAL＋JTA の 737-800 は 56 機（所有 49・リース 7）、グループ LCC の SPRING JAPAN が 6 機（2026-03-31） [JAL 決算資料](https://finance-frontend-pc-dist.west.edge.storage-yahoo.jp/disclosure/20260430/20260430514545.pdf)。ANA は 39 機（所有 26・リース 13、FY2024 末） [ANA 決算資料](https://www.ana.co.jp/group/investors/data/kessan/pdf/2025_04_2.pdf)。計画は会社ごとに別 | 会社ごとの問題に分ける。JAL＋JTA 56 機、ANA 39 機。業界横断の比較は別のユースケースにする |
| 外部工場 5 つから、入場ごとに選ぶ | JAL は 2021 年に GE と 5 年の TrueChoice Overhaul 契約（737-800 48 機、100 基超） [GE](https://www.geaerospace.com/news/press-releases/services/japan-airlines-signs-cfm56-7b-services-agreement-ge)。ANA は MTU Maintenance 珠海と 2032 年末まで延長（737NG 47 機、約 100 基） [MTU](https://www.mtu.de/newsroom/press/latest-press-releases/press-release-detail/mtu-maintenance-and-all-nippon-airways-sign-cfm56-7b-mro-contract/) | 工場選びは入場ごとではなく、長期契約の満了時の判断（数年に一度）。日々の判断は契約の中での入場時期・整備範囲・見積もり承認 |
| グループ内工場が軽い整備（PR）を行う | JAL エンジニアリングのオーバーホール対象は CF6-80C2・GE90・GEnx で、CFM56-7B はナセル修理のみ掲載 [JALEC](https://www.jalec.co.jp/maintenance/)。ANA エンジンテクニクスの対象に CFM56 はない [ANA ETC](https://www.etc.ana-g.com/corporate.html) | 自社で行うのは取卸し時の検査・ボアスコープ・ナセルなどに限る。工場入場は外部 |
| 契約は整備範囲ごとの固定価格 | 主流は実費精算（T&M）と飛行時間単価（RPFH）。GE TrueChoice は Overhaul（T&M）・Flight Hour・Material の 3 種 [GE](https://www.geaerospace.com/commercial/services/true-choice/flight-hour)。飛行時間単価の契約には年次の価格改定、部品価格表への連動、大きな異物損傷の対象外、寿命部品を早く替えたときの「失われた寿命」の請求がある [SEC 開示の契約例](https://www.sec.gov/Archives/edgar/data/948846/000119312503081318/dex105.htm) | 契約の型を 3 つ（実費精算／飛行時間単価／モジュール交換の固定価格）にし、異物・鳥の衝突を別の出来事として実費で扱う |
| 為替リスクは「外国の見積もり」にかかる | 飛行時間単価は米ドル建て（同上） | 為替は米ドル建ての費用全体にかける（収入が円のため） |
| 737-8 は 2027-01 から 2 か月に 1 機 | JAL 737-8 は確定 38 機、受領は 2026 年度後半見込み [JAL](https://press.jal.co.jp/ja/release/202503/008714.html) [Aviation Wire](https://www.aviationwire.jp/archives/328247)。ANA は 30 機、受領は遅れを重ね 2026 年 10 月以降 [Aviation Wire](https://www.aviationwire.jp/archives/335931) | 受領時期を不確かな前提として扱い、遅れの場合（退役延長で整備が増える）を加える |

## 2. 数字の点検

| 項目 | 実務（出典） | 今の仮定 | 評価 |
|---|---|---|---|
| 工場整備 1 回の費用 | 2020 年の例：コアのみ性能回復 2.0M$＋寿命部品 2.0M$、コア＋低圧タービン 3.0M$＋寿命部品 3.0M$ [Ackert, ISTAT 2020](https://www.istat.org/Portals/0/Ackert_ISTAT_LearningLab_pdf.pdf) | PR 2.5 / CORE 5.9 / FULL 9.9 M$ | CORE は 2020 年水準のまま。2026 年換算で 7.5〜8.5M$（推定） |
| 費用の上がり方 | 性能回復 年 4.5〜6.5%、寿命部品 年 5〜8%（ISTAT 2020）、CFM56 の寿命部品は 2023 年に約 12%（Ishka、本文未確認） | 一定 | 材料・工賃・寿命部品の 3 系統で年率を持たせる |
| 寿命部品の寿命 | 高圧系 20,000、低圧タービン 25,000、ファン・ブースター 30,000 EFC。古い仕様には 16,300〜17,900 の短いものがある [Aircraft Commerce 2008](https://www.aircraft-commerce.com/wp-content/uploads/aircraft-commerce-docs1/Aircraft%20guides/CFM56-7B/ISSUE58_CFM56_7B_MTCE.pdf) | コア 20,000 / 低圧 25,000 | ファン・ブースターを分ける |
| 寿命部品一式の価格 | 2008 年 1.78M$、2018 年 3.76M$（19 部品） [Aircraft Commerce 2018](https://www.aircraft-commerce.com/sample_article_folder/120_MTCE_B.pdf)。2026 年は 5.5〜7M$（推定） | 整備費に含めて暗黙 | 別の費用として明示する |
| 排気温度の余裕 | 最初の 1,000 EFC で 11〜15°C 低下、その後 1,000 EFC あたり 4〜6°C。回復後は -7B24 で 70〜80、-7B26 で 42〜48、-7B27 で 39〜44°C（Aircraft Commerce 2008） | 一律 5°C/1,000、回復 55〜62°C | 推力の型を決め、初期の急な低下を入れる |
| 翼についている期間 | -7B26 初回 12,000〜14,000 EFC、成熟期 9,000〜12,000。2 回目は初回の約 65%（同） | 平均 約 10,600 EFC | 平均は妥当。初回と 2 回目以降を分ける |
| 予定外の取卸し | 重い（軸受の故障、鳥・異物）約 0.013/1,000 EFH で最大 2M$、軽い（オイル漏れ、部分修理）約 0.017/1,000 EFH で 25〜30 万$（同） | 0.004/基・月（約 0.015/1,000 EFH） | 重いものだけ相当。2 層に分ける |
| 飛行中のエンジン停止率 | 0.003/1,000 EFH 以下（GE、2006 年） [GE](https://www.geaerospace.com/news/press-releases/joint-ventures/now-thats-reliable-engine) | なし | 信頼性の報告に使う |
| 工期 | コロナ前 約 60 日、現在はオーバーホール 90〜120 日、軽作業 約 45 日 [AerFin 2026-06](https://www.aerfin.com/latest/insights/inside-the-engine-mro-supply-chain-why-repair-delays-are-rising-and-whats-driving-them/)。737NG の中規模作業 100〜120 日 [IBA 2026-07](https://www.iba.aero/resources/articles/engine-mro-rising-demand-limited-capacity/)。最大の詰まりは高圧タービン翼 [Aviation Week 2026-08](https://aviationweek.com/mro/supply-chain/hpt-blade-supply-crunch-slows-cfm56-overhauls) | 3〜6 か月 | 範囲は妥当。整備範囲別の分布にし、タービン翼待ちの遅れを加える |
| 1 飛行時間あたりの整備費 | 2020 年の例から 330〜360 $/EFH、2026 年換算 450〜520（推定） | 429 $/EFH | やや低い〜妥当 |
| 短期リース | 中長期 80〜90k$/月、短期は 10 万ドル前後〜で延長が多い [IBA 2025-10](https://www.iba.aero/resources/articles/iba-engine-value-and-lease-rate-update/)。別に返金されない使用量料金 [Willis Lease 10-K](https://www.sec.gov/Archives/edgar/data/1018164/000101816426000036/wlfc-20251231x10k.htm) | 190k$/月 | 約 2 倍。固定 100〜130k$/月＋使用量料金に |
| グリーンタイム・エンジン | ハーフライフの価値 -7B24 で 5.7M$、-7B27 で 6.4M$（2025 年下期、IBA 同上） | 正味 5,000k$、最大 8 基 | 水準は妥当。数は楽観的、型ごとに分ける |
| 予備エンジンの数 | 業界の目安は取付エンジンの 10% [AviTrader 2025](https://avitrader.com/2025/07/15/how-to-ensure-adequate-spare-engine-coverage/)。メーカーはポアソン分布で信頼水準を満たす台数を計算 [GE 特許](https://patents.google.com/patent/US7082403B2/en)。計画上の工期は約 120 日、現状 180〜200 日 [AviTrader 2026-09](https://avitrader.com/2026/09/23/spare-engine-management/) | 直接は持たない | 取卸し率 × 工期から計算し、10% で確かめる |
| 整備費の水準 | JAL の整備費 FY2023 1,244 億円 → FY2024 1,472 億円（+18%） [有価証券報告書](https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100W1KL.pdf)。ANA の整備部品・外注費 1,860 → 2,410 億円。理由は定時整備の集中、飛行時間精算、円安、退役延長（ANA 決算資料） | — | 上振れの前提を大きく取る |
| 季節性 | 国内線 2024 年 8 月 1,021 万人（利用率 85%）、2025 年 1 月 859 万人（72%） [国交省](https://www.mlit.go.jp/report/press/content/001769718.pdf) | 便の月別係数（8 月 1.12、2 月 0.88） | 形は整合 |

## 3. 抜けている業務と判断

1. **取卸しの原因は 5 種類**：寿命部品の期限、排気温度の余裕の低下、部品の傷み、異物、同じ機体の 2 基を同時に下ろさないための時期ずらし。原因ごとに予測の仕方が違う [QOCO](https://www.qoco.aero/blog/what-triggers-aircraft-engine-removals)
2. **組み立ての目標**：残る寿命部品の短さと、回復させる余裕で飛べる期間をそろえる。寿命部品は総寿命の 5〜15% を残して替えることが多い [Ackert, financiers](https://www.aircraftmonitor.com/uploads/1/5/9/9/15993320/engine_mx_concepts_for_financiers___v2.pdf)
3. **推力を下げる運用**：劣化を遅らせ、1 飛行時間あたりの費用を下げる（同上）
4. **状態監視からの取卸し判断**：自動の警報 → 技術者の判断（点検、ボアスコープ、部品交換、取卸し計画への反映） [EASA IP 177](https://www.easa.europa.eu/download/imrbpb/IP%20177%20-%20Use%20of%20Engine%20Condition%20Monitoring.pdf)
5. **信頼性管理**：月次の報告、警戒値（例：3 か月移動平均の 12 か月平均＋3 標準偏差）、委員会による是正処置の承認 [FAA AC 120-17B](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_120-17B.pdf)。日本では最大離陸重量 5.7t 超に信頼性管理方式が義務 [整備規程審査要領](https://www.mlit.go.jp/notice/noticedata/pdf/201505/00005547.pdf)
6. **技術通報の評価期限、委託先の選定基準と定期監査**（同要領）
7. **繰り返し点検**：ファンブレードの超音波検査の反復間隔が 3,000 から 1,600 サイクルに短縮（AD 2018-18-01） [AerSale](https://www.aersale.com/media-center/faa-mandates-more-frequent-cfm56-7b-engine-inspections)
8. **推力別の寿命部品の記録**、記録の欠けや食い違い [IATA LLP Traceability](https://www.iata.org/contentassets/bf8ca67c8bcd4358b3d004b0d6d0916f/llp-traceability-1st-ed-2020.pdf)
9. **契約・市場の仕組み**：モジュール交換（工期 5〜15 日の固定価格） [Aviation Week](https://aviationweek.com/mro/aircraft-propulsion/will-popularity-engine-module-changes-continue)、エンジンを売って借り戻し、整備リスクごと任せる契約 [Willis Lease 説明資料](https://www.sec.gov/Archives/edgar/data/0001018164/000101816425000055/wlfc1q25presentationfina.htm)、整備積立金と返却時の精算、修理品・中古部品で費用を下げる選択
10. **実際の業務**（各社の公表）：ANA の原動機マネジメント部は「年間のエンジン取り卸し計画を策定」し、社内・海外委託先での修理完了までを管理、修理委託と部品調達、航空局との折衝。2026 年度にデータサイエンスチームを新設 [ANA 採用](https://www.ana.co.jp/group/recruit/ana-recruit/career/globalstaff/interview/conversation06/)。原動機技術チームは整備プログラムの立案と、高額部品の交換時期の判断 [ANA 採用](https://www.ana.co.jp/group/recruit/ana-recruit/interview/talk15.html)

## 4. 出典なし（感度分析の変数として扱う）

最低発注量の条件、寿命部品キットの納期（8/12 か月）、緊急手配の割増（900k$）、プール料金（350k$）、部品取りの価値（1,800k$）、各社の予備エンジン数、取卸し率、飛行中停止率、契約単価、JAL の 2026 年以降の契約先。
