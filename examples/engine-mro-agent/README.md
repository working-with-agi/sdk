# エンジン入場計画を AI エージェントのワークフローとして回す（WorkWithAI SDK）

[`engine-shop-selection-mc`](../engine-shop-selection-mc/)（工場見積もり比較 × モンテカルロの入場計画）の Python 分析を、
**WorkWithAI SDK（`@work-with-ai/sdk`）のセッション上で AI エージェントに実行させる**サンプルです。
分析そのものの中身は第2弾の README を参照してください。ここでは「SDK でこう使える」を示します。

> データは説明用の合成値です。実在の工場・OEM の見積もりではありません。

## 構成

| ファイル | 役割 | 使う SDK 機能 |
|---|---|---|
| `src/config.ts` | 接続先・API キー・ユーザーを環境変数から読む（ハードコードしない） | — |
| `src/ingest.ts` | 入力データ・要望一覧・PDF をナレッジベースへ。工場見積もりフォルダの月次同期を設定 | `KnowledgeClient.upload / remove / connections / connect / resume / sync` |
| `src/run-monthly.ts` | 月次見直しを planner エージェントに実行させ、reviewer ペインを追加 | `WorkAGI.api` → `health / listTools / listSessions / createSession / addPane / getLayout / destroySession`、`KnowledgeClient.context` |
| `src/ui.ts` + `index.html` | 計画担当者の画面。セッションに接続してエージェントの作業を見る・指示する | `WorkAGI.terminal`（xterm.js 描画 + WebSocket） |

## ビジネスユースケースと SDK の対応

REQUIREMENTS.md #17「複数のビジネスユースケースを切り分ける」に対応させた整理です。

| ユースケース | 何を決めるか | このサンプルでの流れ | SDK 機能 |
|---|---|---|---|
| **年間基準計画** | 年間の入場件数・予算の「暗黙の合意」 | `lifecycle.py` の定常値（norms）と初回の `report.json` を `baseline/` に固定 | `createSession`（初回）、`knowledge.upload`（基準を KB に残す） |
| **月次の入場判断** | 今月確定すべきエンジン（判断期限）と基準との差分 | `run-monthly.ts` → planner が `lifecycle → explore → actions → decide → build_room` を実行し `summary.md` | `createSession({tool:"claude", prompt})`、`WorkAGI.terminal` で画面表示 |
| **工場・契約** | 工場選択、最低発注量、特急、見積もり改定の反映 | 同期された見積もり（Drive）を `knowledge.context("shop quote revisions…")` で拾い `runs/<月>/shop_quotes.json` に反映 | `knowledge.connect({provider:"google-drive", schedule})`、`sync` |
| **資産戦略** | 予備エンジン、中寿命エンジン入れ替え、LLP キット先行発注 | `actions.py`（打ち手の効果）と `explore.py`（条件別の答え）を summary に引用 | 同じセッション内で実行（計算は Python 側） |
| **リスク対応** | TAT 遅延・LLP 逼迫・非計画取卸しを受けた再計画 | `knowledge.context("shop TAT delays" / "LLP kit lead time" …)` をプロンプトへ注入。reviewer が要望・マニュアルと照合 | `KnowledgeClient.context`、`addPane({role:"reviewer"})` |

## 実行方法

前提：Node.js 20 以上、WorkWithAI（agiterm-server）への接続情報。エージェント側のコンテナに
このリポジトリと Python 環境（`pip install -r ../engine-shop-selection-mc/requirements.txt`）が必要です。

```bash
cd examples/engine-mro-agent
npm install                      # esbuild / typescript / xterm（SDK をソースから束ねるため）
npm run typecheck                # tsc --noEmit（SDK は ../../packages/core/src を paths で参照）

export WORKWITHAI_ENDPOINT=https://<server>:8600
export WORKWITHAI_API_KEY=<key>          # シークレット。コードやファイルに書かない
export WORKWITHAI_USER=<planner user id>
# 任意: WORKWITHAI_KNOWLEDGE_ENDPOINT（ナレッジハブが別ホストの場合）、WORKWITHAI_ACCESS_TOKEN（Logto JWT）

# 1. ナレッジベースへ取り込み（何度実行しても同じ文書 ID。変更の無いファイルは送らない）
npm run ingest -- --dry-run
npm run ingest -- --pdf-dir ./manuals --drive-folder <Google Drive のフォルダ ID> --sync-now

# 2. 月次見直し（同じ月のセッションが動いていれば二重に作らない）
npm run run-monthly -- --month 2026-10 --dry-run   # プロンプトだけ表示
npm run run-monthly -- --month 2026-10 --watch 30  # 作成後 30 分 health / layout を監視
npm run run-monthly -- --destroy-all               # 後片付け（ラベル engine-mro-monthly-* を削除）

# 3. 計画担当者の画面
npm run serve    # → http://localhost:5173/index.html?session=<session_id>&endpoint=<server>
```

`npm run ingest` / `run-monthly` は esbuild で `dist/node/` に束ねてから `node` で実行します
（理由は下の「SDK の制約」1）。`--workdir` でエージェント側から見た分析フォルダを変えられます（既定 `examples/engine-shop-selection-mc`）。
月次の自動実行は、cron や CI から `npm run run-monthly` を呼んでください（ナレッジ同期は `schedule: "0 3 1 * *"` でその直前に走る設定）。

## 検証済みの範囲 / サーバーが無いと確認できないこと

確認済み：`tsc --noEmit`（SDK ソースを含めて型検査）、esbuild のバンドル、`--dry-run`、
REST を模したローカルのモックサーバーに対する呼び出し順・冪等性（2 回目の ingest はスキップ、同月の二重起動を拒否）。

未確認（本物のサーバーが必要）：
- `createSession` の `prompt` が claude CLI にどう渡るか（初回入力として送られるか）、長いプロンプトの上限
- `addPane` の `role: "reviewer"` の意味づけ、ペインの作業ディレクトリ
- ナレッジの `document_id` 指定での上書き挙動、`remove` の 404、JSON/Markdown の分割品質
- Google Drive 同期の `config` のキー名（ここでは `folder_id` と仮定）と `schedule` の解釈（タイムゾーン）
- ブラウザからの WebSocket 接続（CORS / `api_key` クエリの扱い）

## SDK の制約（このサンプルで回避したもの）

1. `@work-with-ai/sdk` の入口が xterm.js を必ず import するため、Node からそのまま読むと失敗します
   （xterm は CJS で名前付き export が解決できない）。ここでは esbuild で束ねて回避。Node 用の入口（例 `@work-with-ai/sdk/node`）があると素直になります。
2. REST でセッションの出力（`summary.md` や画面の内容）を読む手段、実行中のエージェントに追加の指示を送る手段がありません
   （WebSocket の `WorkAGI.connect().sendInput` はペインを指定できない）。完了判定は画面か成果物で行う前提です。
3. `addPane` に `prompt` が無いため、reviewer への指示は planner が `review-brief.md` を書き、担当者がペインに貼り付けます。
4. `KnowledgeClient` は `WorkAGI` から生成できず、`new KnowledgeClient(endpoint, key)` で直接作ります。
5. セッション・ナレッジ文書にメタデータ（対象月など）を付けられないため、ラベルと文書 ID の命名で区別しています。
