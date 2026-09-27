#!/usr/bin/env python3
"""The entry page: how the yearly plan and the monthly plan map onto the calendar, and
where each question is answered (links into every report and document).

  python build_dashboard.py --track-dir out/track --roll-dir out/roll --html-out out/index.html --docs-out out

Writes the dashboard and, with --docs-out, HTML renderings of the handover documents
(story, requirements, README) it links to. Everything is self-contained UTF-8 HTML.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

import decisions

HERE = Path(__file__).resolve().parent

# which report view answers what, by loop
LOOPS = [
    ("年次の版（つくる・直す）", "年 1 回。前提を実績で引き直し、計画を凍結し、決め方を採点する", [
        ("budget", "年間計画と予算", "report"), ("runout", "退役までの入場列", "report"), ("demand", "客席の需要（一つ上の層）・足す計画", "report"),
        ("fleets", "機種横断（会社全体）", "report"), ("backtest", "過去で検証（バックテスト）", "report"), ("review", "PDCA／OODA の見直し", "report"),
        ("roll", "次の版への引き継ぎ", "report"), ("history", "過去の計画との整合", "report"), ("invest", "国内工場の新設", "report"),
        ("tax", "税引後で比べる", "report"), ("finance", "お金の仕組み", "report"), ("mx4", "積立金と機体価値", "report"), ("annual", "年間計画レポート（別画面）", "annual")]),
    ("月次会議（回す・確かめる）", "月 1 回。計画との一致、前提の確率、乗り換えの価値と判断期限", [
        ("month", "今月からの判断", "report"), ("track", "計画の追跡", "report"), ("cpd", "変化点と前提の整合", "report"), ("playbook", "打ち手の順番と購入計画の輪", "report"),
        ("actions", "打ち手の効果", "report"), ("lease", "リース返却", "report"), ("resilience", "立て直しの安さ", "report"), ("loops", "PDCA と OODA（二つの輪）", "report"),
        ("monthly", "月次レポート（別画面）", "monthly"), ("tracking", "計画の追跡（別画面）", "track")]),
    ("その場（動く）", "当日〜数日。暗黙のルールで決め、会議は乗り換えと安全スイッチだけ", [
        ("quote", "見積もりの承認", "report"), ("trend", "状態監視の警報", "report"), ("spares", "予備エンジンの数", "report"), ("offer", "エンジンの打診", "report"),
        ("cash", "支払いと為替", "report"), ("reliability", "信頼性管理", "report"), ("engines", "エンジン別の明細", "report"), ("sources", "前提と出典", "report")]),
    ("付録（思考の枠組み）", "本文の裏で使っている考え方。読むのは必要なときだけ", [
        ("structure", "計画の構造（基本計画と詳細計画・輪と段階）", "report"), ("loops", "PDCA と OODA（二つの輪）", "report"),
        ("a4", "A4 版レポート（印刷用、付録つき）", "a4")]),
]
FIGS = [("plan_basic.html", "図：基本計画（年次〜半期、PDCA）"), ("plan_detail.html", "図：詳細計画（月次〜当日、OODA）"), ("strategy_stack.html", "図：あるべき分析ストラテジー（流れ）"), ("strategy_matrix.html", "図：あるべき分析ストラテジー（層 × 流れ、右端があるべき結果）"), ("strategy_concept.html", "全体像（ランディングページ）"), ("strategy_grid.html", "全体像の図（5 部門 × 入力・処理・出力、行をクリックで詳細）")]
DOCS = [("story.html", "ストーリー：需要から検証まで", "handover/04_docs/story_需要から検証まで.md"),
        ("design_strategy.html", "概念設計：分析ストラテジーを選ぶ・束ねる（文献つき）", "handover/04_docs/design_分析ストラテジー.md"),
        ("appendix.html", "付録：思考の枠組み・新しい情報の重みづけ・シミュレーションの範囲", "handover/04_docs/appendix_思考の枠組み.md"),
        ("requirements.html", "要件と対応の記録（#1〜）", "REQUIREMENTS.md"),
        ("readme.html", "モデルの説明（README）", "README.md"),
        ("process.html", "進め方（PROCESS）", "handover/04_docs/PROCESS.md"),
        ("practice.html", "実務との距離（PRACTICE）", "handover/04_docs/PRACTICE.md")]
ARTIFACTS = [("https://claude.ai/artifact/QgzfCPy1BF3ngV8QbtRmCz", "Aether Platform パンフレット（A4 三面）"),
             ("https://claude.ai/artifact/X72yEZy4KUYsNw1MnEGx4y", "製品説明デッキ（26 枚）"),
             ("https://claude.ai/artifact/FjXnwkh3qQ6wqA6ddykVkU", "構想デッキ：計画の三層"),
             ("https://claude.ai/artifact/94JGcQgUmxQ22dP6ksjXYx", "レポート（Artifact 版）")]


def md_to_html(md: str, title: str) -> str:
    """A small Markdown renderer: headings, lists, tables, code fences, bold, links."""
    out, in_list, in_code, in_table = [], None, False, False
    inl = lambda t: re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', re.sub(r"`([^`]+)`", r"<code>\1</code>", re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(t))))  # noqa: E731

    def close():
        nonlocal in_list, in_table
        if in_list:
            out.append(f"</{in_list}>"); in_list = None
        if in_table:
            out.append("</tbody></table>"); in_table = False
    for ln in md.splitlines():
        if ln.startswith("```"):
            close(); in_code = not in_code; out.append("<pre>" if in_code else "</pre>"); continue
        if in_code:
            out.append(html.escape(ln)); continue
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            close(); out.append(f"<h{len(m.group(1))}>{inl(m.group(2))}</h{len(m.group(1))}>"); continue
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            if not in_table:
                close(); in_table = True; out.append("<table><thead><tr>" + "".join(f"<th>{inl(c)}</th>" for c in cells) + "</tr></thead><tbody>")
            else:
                out.append("<tr>" + "".join(f"<td>{inl(c)}</td>" for c in cells) + "</tr>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", ln)
        if m:
            if in_list != "ul":
                close(); in_list = "ul"; out.append("<ul>")
            out.append(f"<li>{inl(m.group(1))}</li>"); continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)", ln)
        if m:
            if in_list != "ol":
                close(); in_list = "ol"; out.append("<ol>")
            out.append(f"<li>{inl(m.group(1))}</li>"); continue
        if ln.startswith(">"):
            close(); out.append(f"<blockquote>{inl(ln[1:].strip())}</blockquote>"); continue
        if not ln.strip():
            close(); continue
        close(); out.append(f"<p>{inl(ln)}</p>")
    close()
    css = ("body{margin:0;background:#f6f4ee;color:#141413;font-family:'IBM Plex Sans JP',system-ui,sans-serif;line-height:1.7}"
           "main{max-width:880px;margin:0 auto;padding:40px 24px 80px}h1{font-size:28px}h2{font-size:20px;margin-top:36px;border-bottom:1px solid #cfcbc0;padding-bottom:6px}"
           "h3{font-size:16px;margin-top:24px}table{border-collapse:collapse;font-size:13px;margin:8px 0}th,td{border:1px solid #cfcbc0;padding:4px 8px;text-align:left}"
           "pre{background:#ffffff;border:1px solid #cfcbc0;padding:12px;overflow-x:auto;font-size:12px}code{background:#efece4;padding:0 4px}blockquote{border-left:3px solid #1f3d63;margin:8px 0;padding:4px 12px;color:#5b5a55}"
           "a{color:#1f3d63}.top{font-size:12px;color:#5b5a55}")
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f"<style>{css}</style></head><body><main><p class=\"top\"><a href=\"index.html\">← ダッシュボード</a></p>" + "\n".join(out) + "</main></body></html>")


def company_calendar(cid: str, track_dir: Path | None, roll_dir: Path | None) -> dict:
    b = json.loads((HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    m = b["monthly"]; labels = m["labels"]; H = len(labels)
    deadlines = [sum(1 for r in b["plan"] if r["deadline_t"] == t) for t in range(H)]
    visits = [sum(1 for r in b["plan"] if r["t"] == t) for t in range(H)]
    returns = {}
    for le in (fleet.get("leases") or {}).get("engines", []):
        if le["return_t"] < H:
            returns[le["return_t"]] = returns.get(le["return_t"], 0) + 1
    tr = fleet.get("transition") or {}
    exits = []
    if tr.get("start"):
        y, mo = (int(x) for x in tr["start"].split("-")); y0, m0 = (int(x) for x in fleet["start"].split("-"))
        t0 = (y * 12 + mo - 1) - (y0 * 12 + m0 - 1)
        exits = [t for t in range(t0, H, int(tr.get("every_months", 2)))]
    tracked, as_of, switch_months = 0, None, []
    tp = track_dir / f"{cid}-track-crunch.json" if track_dir else None
    if tp and tp.exists():
        t = json.loads(tp.read_text(encoding="utf-8"))
        tracked = t["actuals"]["months"]; as_of = t["actuals"]["as_of"]
        switch_months = [x["as_of"] for x in t["timeline"] if x.get("hysteresis_ok")]
    nxt = None
    rp = next(iter(sorted(roll_dir.glob(f"{cid}-roll-*.json"))), None) if roll_dir else None
    if rp:
        r = json.loads(rp.read_text(encoding="utf-8")); nxt = r["to_version"]
    return {"id": cid, "name": b["company"]["name"], "version": b["version"], "labels": labels, "fy": m["fy"], "peak": m["peak"],
            "deadlines": deadlines, "visits": visits, "returns": returns, "exits": exits, "tracked": tracked, "as_of": as_of,
            "switch_months": switch_months, "next_version": nxt, "budgets": b["budgets"],
            "spend": {fy: v.get("spend", 0) for fy, v in b["plan_of_record"]["by_fiscal_year"].items()}}


def build_html(cos: list[dict], today: str) -> str:
    data = json.dumps(cos, ensure_ascii=False, separators=(",", ":"))
    loops = json.dumps(LOOPS, ensure_ascii=False)
    dec = json.dumps([[d, m, mat, sc, sec, who, lp] for d, m, mat, sc, sec, who, lp in decisions.DECISIONS], ensure_ascii=False)
    docs = "".join(f'<li><a href="{f}">{html.escape(t)}</a></li>' for f, t, _ in DOCS) + "".join(f'<li><a href="{f}">{html.escape(t)}</a></li>' for f, t in FIGS)
    arts = "".join(f'<li><a href="{u}">{html.escape(t)}</a> <span class="hint">非公開リンク：共有された人だけ開ける</span></li>' for u, t in ARTIFACTS)
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>エンジン計画 ダッシュボード</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;700&display=swap">
<style>
:root{{--ink:#141413;--bg:#f6f4ee;--panel:#ffffff;--rule:#cfcbc0;--muted:#5b5a55;--accent:#1f3d63;--accent-soft:#dfe6f0;--warn:#b7791f;--crit:#a23b2a;--good:#2f5d3a;--ws:#7595bd}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'IBM Plex Sans JP',system-ui,sans-serif;line-height:1.6}}
main{{max-width:1180px;margin:0 auto;padding:32px 24px 80px}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:18px;margin:32px 0 10px}}
.sub{{color:var(--muted);font-size:13px}}.tabs button{{border:1px solid var(--rule);background:var(--panel);padding:6px 14px;border-radius:6px;margin-right:6px;cursor:pointer;font:inherit}}.tabs button[aria-selected=true]{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.panel{{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px 18px;margin:10px 0}}.grid3{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}@media(max-width:860px){{.grid3{{grid-template-columns:1fr}}}}
.loop h3{{margin:0 0 4px;font-size:15px;color:var(--accent)}}.loop p{{margin:0 0 8px;font-size:12px;color:var(--muted)}}.loop ul{{margin:0;padding-left:18px;font-size:13px}}.loop li{{margin:2px 0}}
a{{color:var(--accent)}}.hint{{font-size:11px;color:var(--muted)}}.scroll{{overflow-x:auto}}
table.cal{{border-collapse:collapse;font-size:11px;min-width:1100px}}table.cal th,table.cal td{{border:1px solid var(--rule);padding:3px 4px;text-align:center;white-space:nowrap}}table.cal th.row{{text-align:left;background:var(--bg);min-width:150px}}
td.peak{{background:#f3ede2}}td.fy1{{background:#eef2f7}}.bar{{display:inline-block;height:10px;border-radius:2px;background:var(--accent);width:100%}}.bar.next{{background:var(--ws)}}.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--good)}}.dot.plan{{background:var(--rule)}}
.n{{display:inline-block;min-width:16px;padding:0 3px;border-radius:3px;background:var(--accent-soft);font-weight:700}}.n.hot{{background:#f2d7c5}}.dia{{color:var(--warn)}}.ex{{color:var(--crit);font-weight:700}}
.legend{{font-size:11px;color:var(--muted);margin-top:6px}}.kpi{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.kpi div{{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;font-size:12px}}.kpi b{{display:block;font-size:20px;color:var(--accent)}}
</style></head><body><main>
<h1>エンジン計画 ダッシュボード</h1>
<div class="sub">年次の版と月次の判断を暦の上に重ね、どの問いをどの画面で見るかをまとめた入口。{today} 時点。数値は合成データ（実データと明記したものを除く）。</div>
<div class="tabs" id="tabs" style="margin:14px 0"></div>
<div class="kpi" id="kpi"></div>
<div class="panel" id="watch" style="margin-top:10px"></div>
<h2>年次計画と月次計画のマッピング</h2>
<div class="panel"><div class="scroll" id="cal"></div><div class="legend">帯＝年次の版が覆う期間（濃い＝今の版、淡い＝次の版）。●＝月次会議の実績（灰は予定）。数字＝その月の判断期限の件数（濃い赤は 3 件以上）、入場＝その月に工場に入る件数。◇＝リース返却、▲＝新機の受領（1 機退役）。背景の色は繁忙期と年度の切れ目。</div></div>
<h2>話題ごと</h2>
<div class="sub">前提・指摘・打ち手・例外・引き金を話題に振り分けたもの。会議はこの単位で進める。色は最悪の状態（赤＝今すぐ、黄＝会議で決める、灰＝情報、緑＝問題なし）。</div>
<div class="grid3" id="topics"></div>
<h2>二つの輪と画面</h2>
<div class="grid3" id="loops"></div>
<div class="panel"><h3 style="margin:0 0 6px;font-size:15px">意思決定 → 判断材料 → 画面（レポートとシミュレーション画面の対応）</h3><div style="overflow:auto"><table id="decisions" style="font-size:12px;border-collapse:collapse;width:100%"></table></div></div>
<h2>リンク集</h2>
<div class="grid3">
<div class="panel"><h3 style="margin:0 0 6px;font-size:15px">画面</h3><ul id="pages" style="margin:0;padding-left:18px;font-size:13px"></ul></div>
<div class="panel"><h3 style="margin:0 0 6px;font-size:15px">文書</h3><ul style="margin:0;padding-left:18px;font-size:13px">{docs}</ul></div>
<div class="panel"><h3 style="margin:0 0 6px;font-size:15px">資料（Artifact）</h3><ul style="margin:0;padding-left:18px;font-size:13px">{arts}</ul></div>
</div>
<p class="hint">コード：working-with-agi/sdk の examples/engine-shop-selection-mc（ブランチ claude/aircraft-engine-repair-optimization-8oww5m）。再生成は run_all.sh。</p>
</main>
<script>
const DATA = {data}; const LOOPS = {loops}; const DEC = {dec}; let co = 0;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
const link = (key, kind) => kind === "report" ? `report.html#co=${{co}}&v=${{key}}` : kind === "annual" ? "annual.html" : kind === "a4" ? "report_a4.html" : kind === "monthly" ? "monthly.html" : "track.html";
function render() {{
  const c = DATA[co];
  $("tabs").innerHTML = DATA.map((x, i) => `<button type="button" role="tab" aria-selected="${{i === co}}" data-i="${{i}}">${{esc(x.name)}}</button>`).join("");
  $("tabs").querySelectorAll("button").forEach((b) => (b.onclick = () => {{ co = +b.dataset.i; render(); }}));
  const due3 = c.deadlines.slice(0, 3).reduce((a, b) => a + b, 0), fys = Object.keys(c.budgets);
  $("kpi").innerHTML = `<div>今の版<b>${{esc(c.version)}}</b>窓 ${{c.labels[0]}}〜${{c.labels[c.labels.length - 1]}}</div><div>月次会議の実績<b>${{c.tracked}} か月</b>${{c.as_of ? "最新 " + c.as_of : "—"}}</div><div>3 か月以内の判断期限<b>${{due3}} 件</b>計画の入場 ${{c.visits.reduce((a, b) => a + b, 0)}} 件</div><div>次の版<b>${{esc(c.next_version || "—")}}</b>${{fys.map((f) => `${{f}} ${{(c.spend[f] / 1000).toFixed(0)}}/${{(c.budgets[f] / 1000).toFixed(0)}}`).join("、")}} 百万ドル（見込み/予算）</div>`;
  const sh = c.shortage;
  $("watch").innerHTML = sh ? `<div style="display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap"><div style="flex:none;padding:6px 12px;border-radius:6px;color:#fff;background:${{sh.triggered ? "var(--crit)" : "var(--good)"}};font-weight:700">エンジン不足の見張り</div><div style="font-size:13px"><b>${{esc(sh.verdict)}}</b><div class="hint">${{esc(sh.as_of)}} 時点：工場に ${{sh.in_shop_now}} 基、これから入場 ${{sh.planned_to_come}} 基。6 か月先まで：${{sh.months.map((x) => `${{x.label.slice(2)}} ${{(x.p_aog * 100).toFixed(0)}}%（余力 ${{x.margin_mean >= 0 ? "+" : ""}}${{x.margin_mean.toFixed(0)}}）`).join("、")}}。${{esc(sh.rule)}}</div><div class="hint">必要エンジン数の出所：${{esc(c.schedule_source)}}</div></div></div>` : "";
  const H = c.labels.length, y0 = +c.labels[0].slice(0, 4), m0 = +c.labels[0].slice(5);
  const nextT = c.next_version ? ((+c.next_version.slice(0, 4)) * 12 + (+c.next_version.slice(5)) - 1) - (y0 * 12 + m0 - 1) : null;
  const th = c.labels.map((l, t) => `<th class="${{c.peak[t] ? "peak" : ""}} ${{c.fy[t] !== c.fy[0] && c.fy[t] === c.fy[Math.min(H - 1, t)] && c.fy[t] !== c.fy[t - 1] ? "fy1" : ""}}">${{l.slice(2)}}</th>`).join("");
  const rowFy = c.fy.map((f, t) => t === 0 || f !== c.fy[t - 1] ? `<td colspan="${{c.fy.filter((x) => x === f).length}}"><b>${{f}}</b> 予算 ${{(c.budgets[f] / 1000).toFixed(0)}} 百万ドル</td>` : "").join("");
  const rowVer = c.labels.map((l, t) => `<td><span class="bar" title="${{esc(c.version)}} 版"></span></td>`).join("");
  const rowNext = c.labels.map((l, t) => `<td>${{nextT != null && t >= nextT ? `<span class="bar next" title="${{esc(c.next_version)}} 版（予定）"></span>` : ""}}</td>`).join("");
  const rowMeet = c.labels.map((l, t) => `<td><span class="dot ${{t < c.tracked ? "" : "plan"}}" title="${{l}} 月次会議${{t < c.tracked ? "（実績）" : "（予定）"}}"></span>${{c.switch_months.includes(l) ? ' <span class="ex" title="乗り換えの判断">⇄</span>' : ""}}</td>`).join("");
  const rowDue = c.deadlines.map((n, t) => `<td>${{n ? `<span class="n ${{n >= 3 ? "hot" : ""}}">${{n}}</span>` : ""}}</td>`).join("");
  const rowVis = c.visits.map((n) => `<td>${{n || ""}}</td>`).join("");
  const rowEv = c.labels.map((l, t) => `<td>${{c.returns[t] ? `<span class="dia" title="リース返却 ${{c.returns[t]}} 基">◇${{c.returns[t] > 1 ? c.returns[t] : ""}}</span>` : ""}}${{c.exits.includes(t) ? `<span class="ex" title="新機の受領・1 機退役">▲</span>` : ""}}</td>`).join("");
  const rowLink = c.labels.map((l, t) => `<td><a href="monthly.html" title="月次レポート">月</a> <a href="track.html" title="計画の追跡">追</a></td>`).join("");
  $("cal").innerHTML = `<table class="cal"><thead><tr><th class="row">月</th>${{th}}</tr></thead><tbody>
    <tr><th class="row">年度と予算</th>${{rowFy}}</tr>
    <tr><th class="row">年次の版（今）</th>${{rowVer}}</tr>
    <tr><th class="row">年次の版（次）</th>${{rowNext}}</tr>
    <tr><th class="row">月次会議</th>${{rowMeet}}</tr>
    <tr><th class="row">判断期限（件）</th>${{rowDue}}</tr>
    <tr><th class="row">入場（件）</th>${{rowVis}}</tr>
    <tr><th class="row">返却・受領</th>${{rowEv}}</tr>
    <tr><th class="row">その月の画面</th>${{rowLink}}</tr></tbody></table>`;
  const SEVC = {{ crit: "var(--crit)", warn: "var(--warn)", info: "var(--muted)", ok: "var(--good)" }};
  $("topics").innerHTML = (c.topics || []).map((t) => {{
    const ov = t.assumptions.filter((a) => a.status !== "ok");
    const top = t.findings.filter((f) => f.severity !== "ok").slice(0, 3).map((f) => `<li><span style="background:${{SEVC[f.severity]}};display:inline-block;width:8px;height:8px;border-radius:2px"></span> ${{esc(f.finding)}}</li>`).join("");
    const acts = t.actions.map((x) => `<li>${{esc(x.label)}}（${{esc(x.who)}}、${{x.expected_delta_k != null ? (x.expected_delta_k / 1000).toFixed(1) + " 百万ドル" : "—"}}）</li>`).join("");
    const trig = t.triggers.map((x) => `<li>引き金：${{esc(x.name)}} — ${{esc(x.evidence)}}</li>`).join("");
    const ex = t.exceptions.length ? `<li>追跡の例外 ${{t.exceptions.length}} 件（直近 ${{esc(t.exceptions[t.exceptions.length - 1].as_of)}} ${{esc(t.exceptions[t.exceptions.length - 1].kind)}}）</li>` : "";
    return `<div class="panel loop" style="border-left:4px solid ${{SEVC[t.status]}}"><h3>${{esc(t.name)}} <span class="hint">${{esc(t.owner)}}</span></h3><p>${{esc(t.what)}}</p>
      <div class="hint" style="margin-bottom:6px">前提 ${{t.counts.assumptions}}${{ov.length ? `（要見直し ${{ov.length}}）` : ""}}・指摘 ${{t.counts.findings}}・打ち手 ${{t.counts.actions}}・例外 ${{t.counts.exceptions}}</div>
      <ul>${{trig}}${{top}}${{acts}}${{ex}}</ul>
      <div class="hint" style="margin-top:6px">画面：${{t.views.map((v) => `<a href="report.html#co=${{co}}&v=${{v}}">${{v}}</a>`).join(" · ")}}</div></div>`;
  }}).join("");
  $("decisions").innerHTML = `<thead><tr>${{["決めること", "分析", "判断材料", "画面", "A4 の章", "誰が・いつ", "輪"].map((h) => `<th style="text-align:left;border-bottom:1px solid var(--rule);padding:4px 6px">${{h}}</th>`).join("")}}</tr></thead><tbody>` + DEC.map(([d, m, mat, sc, sec, who, lp]) => `<tr>${{[`<b>${{esc(d)}}</b>`, esc(m), esc(mat), sc.map(([k, l]) => `<a href="${{link(k, k === "annual" ? "annual" : k === "monthly" ? "monthly" : k === "tracking" ? "track" : "report")}}">${{esc(l)}}</a>`).join("、"), esc(sec), esc(who), esc(lp)].map((x) => `<td style="padding:4px 6px;border-bottom:1px solid var(--rule);vertical-align:top">${{x}}</td>`).join("")}}</tr>`).join("") + "</tbody>";
  $("loops").innerHTML = LOOPS.map(([title, what, items]) => `<div class="panel loop"><h3>${{esc(title)}}</h3><p>${{esc(what)}}</p><ul>${{items.map(([k, label, kind]) => `<li><a href="${{link(k, kind)}}">${{esc(label)}}</a></li>`).join("")}}</ul></div>`).join("");
  $("pages").innerHTML = [["report.html#co=" + co, "エンジン整備レポート（4 段：結論 → ユースケース → 明細 → 前提と出典）"], ["annual.html", "年間計画レポート"], ["monthly.html", "月次レポート"], ["track.html", "計画の追跡"]].map(([h, t]) => `<li><a href="${{h}}">${{esc(t)}}</a></li>`).join("");
}}
render();
</script></body></html>'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", nargs="+", default=["jal", "ana"])
    ap.add_argument("--track-dir", type=Path)
    ap.add_argument("--roll-dir", type=Path)
    ap.add_argument("--topics-dir", type=Path, help="directory with <company>.json (topics.py output)")
    ap.add_argument("--shortage-dir", type=Path, help="directory with <company>.json (shortage.py output)")
    ap.add_argument("--html-out", type=Path, default=Path("index.html"))
    ap.add_argument("--docs-out", type=Path, help="directory to write the document HTML pages into")
    a = ap.parse_args(argv)
    cos = [company_calendar(c, a.track_dir, a.roll_dir) for c in a.companies]
    for c in cos:
        tp = a.topics_dir / f"{c['id']}.json" if a.topics_dir else None
        c["topics"] = json.loads(tp.read_text(encoding="utf-8"))["threads"] if tp and tp.exists() else []
        sp = a.shortage_dir / f"{c['id']}.json" if a.shortage_dir else None
        c["shortage"] = json.loads(sp.read_text(encoding="utf-8")) if sp and sp.exists() else None
        fleet = json.loads((HERE / "data" / c["id"] / "fleet.json").read_text(encoding="utf-8"))
        c["schedule_source"] = fleet.get("schedule_source", "")
    a.html_out.write_text(build_html(cos, date.today().isoformat()), encoding="utf-8")
    n = 0
    if a.docs_out:
        a.docs_out.mkdir(parents=True, exist_ok=True)
        for f, t, src in DOCS:
            p = HERE / src
            if p.exists():
                (a.docs_out / f).write_text(md_to_html(p.read_text(encoding="utf-8"), t), encoding="utf-8"); n += 1
        import figures
        for (f, t), (k, svg) in zip(FIGS, {**figures.svgs(), **figures.extra_svgs()}.items()):
            (a.docs_out / f).write_text(figures.page(svg, t), encoding="utf-8"); n += 1
        (a.docs_out / "strategy_concept.html").write_text(figures.concept_page(), encoding="utf-8"); n += 1
        (a.docs_out / "strategy_grid.html").write_text(figures.concept_grid_page(), encoding="utf-8"); n += 1
    print(f"dashboard -> {a.html_out} ({a.html_out.stat().st_size // 1024} KB), {n} document pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
