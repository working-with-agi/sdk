/**
 * Monthly re-plan of engine shop visits as an AI-agent session.
 *
 *   npm run run-monthly -- --month 2026-10                 # start planner + reviewer
 *   npm run run-monthly -- --month 2026-10 --dry-run       # print the prompt, no network calls
 *   npm run run-monthly -- --month 2026-10 --watch 30      # then poll health/layout for 30 min
 *   npm run run-monthly -- --destroy <session_id>          # clean up one session
 *   npm run run-monthly -- --destroy-all                   # clean up every "engine-mro-monthly" session
 *
 * What happens
 *   1. health() + listTools() — is the server up and is the "claude" CLI available?
 *   2. KnowledgeClient.context() for the questions that change the plan most month to month
 *      ("shop TAT delays", "LLP kit lead time", ...) — the excerpts go into the prompt, so the
 *      agent never needs the API key.
 *   3. createSession({ user_id, tool: "claude", label, prompt }) — the planner runs the Python
 *      pipeline in ../engine-shop-selection-mc and writes the summary.
 *   4. addPane({ tool: "claude", role: "reviewer" }) — a second agent in the same workspace
 *      that checks the plan against REQUIREMENTS.md and the manuals in the knowledge base.
 *   5. Prints session_id / ws_url / pane ids (also saved to last-session.json for ui.ts),
 *      optionally polls health() and getLayout().
 */
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { parseArgs } from "node:util";

import { KnowledgeClient, WorkAGI } from "@work-with-ai/sdk";
import type { AgiApiClient, KnowledgeContextResponse, PaneInfo, SessionInfo } from "@work-with-ai/sdk";

import { exampleRoot, loadConfig, redact } from "./config.js";

const LABEL_PREFIX = "engine-mro-monthly";
const EXAMPLE_ROOT = exampleRoot(import.meta.url);

/** Knowledge-base questions whose answers move the plan from one month to the next. */
const CONTEXT_QUERIES = [
  "shop TAT delays",
  "LLP kit lead time",
  "shop quote revisions and expedite fees",
  "unscheduled engine removals this month",
];
const CONTEXT_CHARS = 1500; // per query, to keep the prompt bounded

function defaultMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

async function fetchContext(kb: KnowledgeClient | null): Promise<string> {
  if (!kb) return "(dry run: knowledge context not fetched)";
  const parts: string[] = [];
  for (const q of CONTEXT_QUERIES) {
    try {
      const r: KnowledgeContextResponse = await kb.context(q, 5);
      const text = r.context.trim();
      parts.push(`### ${q}\n${text ? text.slice(0, CONTEXT_CHARS) : "(該当なし)"}`);
    } catch (e) {
      parts.push(`### ${q}\n(取得失敗: ${e instanceof Error ? e.message : String(e)})`);
    }
  }
  return parts.join("\n\n");
}

/** The planner's instructions. Commands and file names match engine-shop-selection-mc. */
export function plannerPrompt(opts: { month: string; workdir: string; baseline: string; context: string }): string {
  const run = `runs/${opts.month}`;
  const fleet = `${run}/fleet_visits.json`;
  return `あなたはエンジン整備計画（CFM56-7B / 737-800）の月次見直し担当エージェントです。対象月: ${opts.month}
作業ディレクトリ: ${opts.workdir}（engine-shop-selection-mc。README.md と REQUIREMENTS.md を最初に読むこと）

## 0. 今月の前提の変化（ナレッジベースからの抜粋）
${opts.context}

上の抜粋に工場 TAT の遅延、LLP キットのリードタイム、見積もり改定があれば、どの入力値に効くかを整理すること：
- data/shop_quotes.json の shops[].delay.shop_months / shop_probs（工場混雑）、shops[].quotes.{PR,CORE,FULL}.price / tat、shops[].expedite
- data/fleet_visits.json の llp_kits.lead_time_months / on_hand
data/ の原本は変更しない。変更は下の 1b で ${run}/ 配下のコピーにだけ入れ、根拠（抜粋の文書名）を ${run}/overrides.md に記録する。

## 1. 分析パイプラインを実行する（順番どおり、各ステップの終了コードを確認）
\`\`\`bash
cd ${opts.workdir}
mkdir -p ${run}
# 1a. 20 年ライフサイクルの定常値（年間の暗黙の合意）と、今月時点の 2 年窓の入力
python lifecycle.py --json-out ${run}/lifecycle.json --fleet-out ${fleet}
cp data/shop_quotes.json ${run}/shop_quotes.json
\`\`\`
1b. 0. で整理した変更を ${fleet}（llp_kits など）と ${run}/shop_quotes.json に反映する（無ければそのまま）。
\`\`\`bash
# 1c. 確定できないパラメーターの分類 → 打ち手の効果 → 報告書 → 判断ルーム
python explore.py  --fleet ${fleet} --shops ${run}/shop_quotes.json --json-out ${run}/explore.json
python actions.py  --fleet ${fleet} --shops ${run}/shop_quotes.json --json-out ${run}/actions.json
python decide.py   --fleet ${fleet} --shops ${run}/shop_quotes.json --explore ${run}/explore.json --actions ${run}/actions.json \\
                   --levers ${run}/levers.json --sensitivity ${run}/sensitivity.json \\
                   --json-out ${run}/report.json --html-out ${run}/report.html
python build_room.py --report ${run}/report.json --actions ${run}/actions.json --explore ${run}/explore.json \\
                     --html-out ${run}/room.html
\`\`\`
（levers.json / sensitivity.json は任意入力。無ければ decide.py は読み飛ばす。時間が足りなければ
explore.py / actions.py に --scenarios を小さく指定してよいが、その場合は summary に明記。）

## 2. 今月の結論をまとめる → ${run}/summary.md（日本語）
1. **今月決めること**：report.json の urgency.engines のうち status == "now" のエンジン（ESN、判断期限、
   推奨の工場・ワークスコープ・入場月、急いだ／待った場合のコスト差）。status == "soon" は「来月以降の予告」として別掲。
2. **承認事項**：report.json の approvals と conclusion。
3. **基準との差分**：基準計画 ${opts.baseline}/report.json がある場合、推奨案・期待総コスト・P90・欠航確率・
   年度予算の消化・工場別件数・入場月の変わったエンジンを表にする。lifecycle.json の norms（年間の暗黙の合意値）とも比較。
   基準が無い場合は今回の report.json を ${opts.baseline}/ にコピーして「基準を作成」と書く。
4. **前提の変化**：0. で反映した値と、それが結論をどう動かしたか（explore.json の分類で閾値をまたいだか）。
5. 期限前取卸しの例外（report.json の exceptions）は理由付きで列挙。

## 3. レビュー依頼
${run}/review-brief.md に、レビュアーが確認すべき点（前提を変えた箇所、要望の優先順位を緩めた箇所、
例外、数値の出典）を箇条書きで書く。同じワークスペースの reviewer ペインがこれを読む。

## 守ること
- 耐空性（取卸し期限・要監視エンジン）は緩めない。要望が衝突したら REQUIREMENTS.md と report.json の priority に従い下位から緩める。
- 数値は必ず出力ファイルから引用し、推測で埋めない。データは合成値であることを summary 冒頭に明記。
- 最後に「完了: ${run}/summary.md」と 1 行出力する。`;
}

/** The reviewer's instructions (AddPaneParams has no prompt field — see README「SDK の制約」). */
export function reviewerBrief(month: string): string {
  const run = `runs/${month}`;
  return `あなたはレビュアーです。${run}/review-brief.md と ${run}/summary.md を読み、次を確認して ${run}/review.md に書いてください。
- REQUIREMENTS.md の要望（特に #5 今決めること, #8 結論, #9 優先順位, #10 基数・バッファ・要監視, #11 例外の理由）を満たしているか
- 推奨の工場・ワークスコープが shop_quotes.json の quotes と slots、LLP キット制約に反していないか
- 整備マニュアル・WSPG・契約（ナレッジベースに取り込み済みの PDF）と矛盾しないか。根拠の文書名を書く
- summary の数値が ${run}/report.json と一致するか
判定は「承認可 / 条件付き / 差し戻し」のいずれか。`;
}

async function destroy(api: AgiApiClient, ids: string[]): Promise<void> {
  for (const id of ids) {
    await api.destroySession(id);
    console.log(`destroyed ${id}`);
  }
}

async function watch(api: AgiApiClient, sessionId: string, minutes: number): Promise<void> {
  const until = Date.now() + minutes * 60_000;
  while (Date.now() < until) {
    let line = new Date().toISOString().slice(11, 19);
    try {
      line += ` health=${(await api.health()).status}`;
      const alive = (await api.listSessions()).some((s) => s.session_id === sessionId);
      line += ` session=${alive ? "alive" : "gone"}`;
      if (!alive) {
        console.log(line);
        return;
      }
      const layout = await api.getLayout(sessionId);
      line += ` layout=${JSON.stringify(layout.layout).slice(0, 120)}`;
    } catch (e) {
      line += ` error=${e instanceof Error ? e.message : String(e)}`;
    }
    console.log(line);
    await sleep(30_000);
  }
}

async function main(): Promise<void> {
  const { values } = parseArgs({
    options: {
      month: { type: "string", default: defaultMonth() },
      // path of engine-shop-selection-mc as seen from inside the agent's session
      workdir: { type: "string", default: "examples/engine-shop-selection-mc" },
      baseline: { type: "string", default: "baseline" },
      "no-reviewer": { type: "boolean", default: false },
      watch: { type: "string" },
      destroy: { type: "string", multiple: true },
      "destroy-all": { type: "boolean", default: false },
      "dry-run": { type: "boolean", default: false },
    },
  });
  const month = values.month!;
  if (!/^\d{4}-\d{2}$/.test(month)) throw new Error(`--month は YYYY-MM 形式: ${month}`);
  const label = `${LABEL_PREFIX}-${month}`;

  if (values["dry-run"]) {
    console.log(plannerPrompt({ month, workdir: values.workdir!, baseline: values.baseline!, context: await fetchContext(null) }));
    console.log("\n--- reviewer ---\n" + reviewerBrief(month));
    return;
  }

  const cfg = loadConfig();
  const api = WorkAGI.api(cfg.endpoint, cfg.apiKey);
  const kb = new KnowledgeClient(cfg.knowledgeEndpoint, cfg.apiKey);
  if (cfg.accessToken) {
    api.setAccessToken(cfg.accessToken);
    kb.setAccessToken(cfg.accessToken);
  }
  console.log(`endpoint: ${cfg.endpoint}  user: ${cfg.userId}  api key: ${redact(cfg.apiKey)}`);

  // --- clean-up modes -------------------------------------------------------------------
  if (values.destroy?.length || values["destroy-all"]) {
    const ids = values["destroy-all"]
      ? (await api.listSessions()).filter((s) => s.label.startsWith(LABEL_PREFIX)).map((s) => s.session_id)
      : values.destroy!;
    await destroy(api, ids);
    return;
  }

  // --- 1. preflight ---------------------------------------------------------------------
  const health = await api.health();
  const tools = await api.listTools();
  if (!tools.claude?.available) {
    throw new Error(`server has no available "claude" tool: ${JSON.stringify(Object.keys(tools))}`);
  }
  const running = (await api.listSessions()).filter((s) => s.label === label);
  if (running.length) {
    // one planning session per month: do not start a duplicate
    console.log(`already running for ${month}: ${running.map((s) => s.session_id).join(", ")} (use --destroy to restart)`);
    return;
  }
  console.log(`health: ${health.status}  claude: ${tools.claude.binary}`);

  // --- 2. context -----------------------------------------------------------------------
  const context = await fetchContext(kb);

  // --- 3. planner -----------------------------------------------------------------------
  const session: SessionInfo = await api.createSession({
    user_id: cfg.userId,
    tool: "claude",
    label,
    cols: 160,
    rows: 48,
    prompt: plannerPrompt({ month, workdir: values.workdir!, baseline: values.baseline!, context }),
  });
  console.log(`planner session: ${session.session_id}  backend=${session.backend_type ?? "?"}`);
  console.log(`ws_url:          ${session.ws_url}`);

  // --- 4. reviewer ----------------------------------------------------------------------
  let reviewer: PaneInfo | undefined;
  if (!values["no-reviewer"]) {
    reviewer = await api.addPane(session.session_id, { tool: "claude", role: "reviewer" });
    console.log(`reviewer pane:   ${reviewer.pane_id} (${reviewer.title})`);
    console.log("reviewer の指示（ペインに貼り付ける。REST ではペインに prompt を渡せない）:\n" + reviewerBrief(month));
  }

  // for ui.ts / the next run (no secrets in this file)
  await writeFile(
    join(EXAMPLE_ROOT, "last-session.json"),
    JSON.stringify({ month, session_id: session.session_id, ws_url: session.ws_url, reviewer_pane: reviewer?.pane_id ?? null }, null, 2) + "\n",
  );
  console.log(`\n画面: http://localhost:5173/index.html?session=${session.session_id}（README「計画担当者の画面」）`);

  // --- 5. watch -------------------------------------------------------------------------
  if (values.watch) await watch(api, session.session_id, Number(values.watch));
}

main().catch((e: unknown) => {
  console.error(e instanceof Error ? e.message : e);
  process.exitCode = 1;
});
