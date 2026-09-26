# 航空エンジン整備計画の統合最適化（取卸し時期 × ワークスコープ × 予備エンジン）

WorkWithAI SDK のサンドボックス AI ターミナルからエージェントが実行することを想定した、
混合整数線形計画（MILP）モデルのリファレンス実装です。
フリート全体について、各エンジンを **いつ取り卸し、どのワークスコープで整備し、
その間の穴を自社予備エンジン／リースでどう埋めるか** を多期間で同時に決めます。

> データ (`data/sample_fleet.json`) は説明用の合成データです。OEM・実機の値ではありません。

## モデル概要

| 要素 | 内容 |
|---|---|
| 期間 | 月次、既定 48 か月 |
| 決定変数 | `x[e,t,w]` 入場（ワークスコープ w）, `u[e,t]` 稼働, `L[t]` リース台数, `s[t]` AOG, `y[e,t]` 装着イベント |
| 状態 | `g[e,t]` EGT マージン [°C], `r[e,m,t]` モジュール別 LLP 残寿命 [cycles] |
| 劣化 | 稼働月ごとに EGT マージン −δ、LLP −c cycles |
| 整備 | ワークスコープごとに EGT をある水準へ回復、指定モジュールの LLP をリセット、TAT か月使用不可 |
| 制約 | 稼働・整備・棚置きの排他、装着位置の充足（自社＋リース＋AOG）、ショップ同時入場枠、EGT/LLP ≥ 0 |
| 目的 | 割引後の（整備費 ＋ リース費 ＋ 載せ替え費 ＋ AOG ペナルティ ＋ 劣化による燃料増分）− 期末資産価値 |

状態変数は「上界のみ・整備時にリセット」で線形化しています。目的関数のどの項も
`g`・`r` が大きいほど得になるため、ソルバーは常に物理的な上限値を取り、この緩和は厳密です。

```
g[e,t+1] ≤ g[e,t] − δ_e·u[e,t] + Σ_{w∈回復} R_w·x[e,t,w]
g[e,t+1] ≤ R_w + (Gmax − R_w)(1 − x[e,t,w])          ∀w∈回復
r[e,m,t+1] ≤ r[e,m,t] − c_e·u[e,t] + Life_m·Σ_{w∋m} x[e,t,w]
u[e,t] + Σ_w Σ_{τ=t−TAT_w+1..t} x[e,τ,w] ≤ 1
Σ_e u[e,t] + L[t] + s[t] ≥ 装着位置数
f[e,t] ≥ φ·(Gmax·u[e,t] − g[e,t])                       （劣化エンジンの燃料増分）
```

詳細はコード (`engine_mro/model.py`) とドキュメントサイトの Showcase ページを参照してください。

## 実行

```bash
pip install -r requirements.txt
python solve.py data/sample_fleet.json                     # HiGHS（既定）
python solve.py data/sample_fleet.json --threads 4         # 並列探索
python solve.py data/sample_fleet.json --solver scip       # SCIP（OR-Tools 経由）
python solve.py data/sample_fleet.json --shop-slots 1 --lease-cost 250 --json-out plan.json
python -m unittest discover -s tests                       # 小規模インスタンスでの検証
```

出力には、コスト内訳、入場計画（取卸し時の EGT マージン・LLP 残寿命）、エンジン別ガントチャート、
および **下界と絶対ギャップ** が含まれます。

### ギャップの読み方

`gap = 主値 − 下界` は「現在の計画が最適から最大でどれだけ離れうるか」の証明済み上限です。
目的関数は大きな期末資産価値クレジットを差し引いた純額なので、相対ギャップ
（`gap / |主値|`）は大きく見えがちです。絶対値（k$）で判断してください。

## WorkWithAI SDK からの利用

```ts
import { WorkAGI, KnowledgeClient } from "@work-with-ai/sdk";

const api = WorkAGI.api(endpoint, apiKey);
const knowledge = new KnowledgeClient(endpoint, apiKey);

// フリートデータ・ショップマニュアルをナレッジへ
await knowledge.upload(new Blob([fleetJson], { type: "application/json" }), "fleet-2026Q4");

// サンドボックス内のエージェントにモデル実行を依頼
const session = await api.createSession({
  user_id: "planner-1",
  tool: "claude",
  label: "engine-mro-plan",
  prompt:
    "examples/engine-mro-optimization で solve.py を実行し、" +
    "ショップ枠 1/2/3 の感度分析と推奨計画を報告して",
});

// 計画担当者の画面にターミナルを埋め込む
WorkAGI.terminal({ container: "#terminal", endpoint, apiKey, sessionId: session.session_id });
```

## 拡張の方向性

- 非計画取卸し（バードストライク・FOD 等）を考慮した確率計画／ロバスト最適化
- ローリングホライズン運用（毎月再最適化し、直近数か月のみ確定）
- エンジン単位の列生成（Dantzig–Wolfe 分解）による強い LP 緩和
- 複数ショップ・外注先の選択、モジュール単位のショップ内ルーティング
