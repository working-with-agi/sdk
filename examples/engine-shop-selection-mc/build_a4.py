#!/usr/bin/env python3
"""The A4 report: the whole story on paper, conclusions first, the thinking framework in the
appendix. One HTML file with print CSS (A4, page breaks, landscape pages for the two structure
figures); render to PDF with Chromium (--pdf).

  python build_a4.py --out-dir out --html-out out/report_a4.html [--pdf out/report_a4.pdf]

Inputs are the pipeline outputs in --out-dir (deltas, hist, roll, runout, review, demand,
backtest, playbook, purchase, shortage, track, invest) and the baselines. Everything is
synthetic data; the page says so on every sheet.
"""

from __future__ import annotations

import argparse
import html as H
import json
import sys
from datetime import date
from pathlib import Path

import build_report as br
import build_dashboard as bd
import figures
import decisions

HERE = Path(__file__).resolve().parent
COS = ["jal", "ana"]


def esc(x) -> str:
    return H.escape("" if x is None else str(x))


def musd(k) -> str:
    return f"{k / 1000:,.1f}"


def pct(x, d=1) -> str:
    return f"{x * 100:.{d}f}%"


def load(out: Path, rel: str):
    p = out / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def company_bundle(out: Path, cid: str) -> dict:
    c = br.company(HERE / "baselines" / f"{cid}-2026-10.json", out / "deltas" / f"{cid}-deltas.json",
                   HERE / "data" / cid / "actuals_backlog.json", out / "invest.json",
                   out / "hist" / f"{cid}-history.json", next(iter(sorted((out / "roll").glob(f"{cid}-roll-*.json"))), None),
                   out / "runout" / f"{cid}.json", out / "review" / f"{cid}.json", out / "demand" / f"{cid}.json",
                   out / "backtest" / f"{cid}.json")
    c["shortage"] = load(out, f"shortage/{cid}.json")
    c["track_crunch"] = load(out, f"track/{cid}-track-crunch.json")
    c["plan_from_demand"] = load(out, f"demand/{cid}-plan.json")
    c["growth"] = load(out, f"growth/{cid}.json")
    return c


# ---------------------------------------------------------------- small charts (static SVG)
def bars(rows: list[tuple[str, float, float | None]], W=520, unit="", fmt=lambda v: f"{v:,.0f}") -> str:
    """Horizontal bars with an optional reference tick per row."""
    L, R, rh = 92, 60, 22
    top = max(max(v, r or 0) for _, v, r in rows) * 1.08 or 1
    x = lambda v: L + v / top * (W - L - R)
    s = []
    for i, (lab, v, ref) in enumerate(rows):
        y = 4 + i * rh
        s.append(f'<text x="{L - 6}" y="{y + 14}" text-anchor="end" class="lbl">{esc(lab)}</text>')
        s.append(f'<rect x="{L}" y="{y + 3}" width="{x(v) - L:.1f}" height="14" rx="2" fill="{"#b0362d" if ref and v > ref * 1.05 else "#274c77"}"/>')
        if ref:
            s.append(f'<line x1="{x(ref):.1f}" x2="{x(ref):.1f}" y1="{y}" y2="{y + 20}" stroke="#13202c" stroke-width="2"/>')
        s.append(f'<text x="{x(max(v, ref or 0)) + 5:.1f}" y="{y + 14}" class="lbl">{fmt(v)}{unit}</text>')
    return f'<svg viewBox="0 0 {W} {len(rows) * rh + 8}" class="chart">{"".join(s)}</svg>'


def line_steps(traj: list[dict], W=520, H=170) -> str:
    """Purchase loop: AOG (line, left axis) and cost (bars, right) per step."""
    L, R, T, B = 40, 40, 22, 24
    n = len(traj)
    if n < 2:
        return ""
    aog = [t["expected"]["aog_prob"] for t in traj]; cost = [t["expected"]["total_cost"] / 1000 for t in traj]
    xa = lambda i: L + i / (n - 1) * (W - L - R)
    ya = lambda v: T + (1 - v / max(aog)) * (H - T - B)
    yc = lambda v: T + (1 - v / max(cost)) * (H - T - B)
    s = [f'<rect x="{xa(i) - 12}" y="{yc(c):.1f}" width="24" height="{H - B - yc(c):.1f}" fill="#dde7f2"/>' for i, c in enumerate(cost)]
    s.append(f'<polyline fill="none" stroke="#b0362d" stroke-width="2" points="{" ".join(f"{xa(i):.1f},{ya(a):.1f}" for i, a in enumerate(aog))}"/>')
    for i, (a, c) in enumerate(zip(aog, cost)):
        s.append(f'<circle cx="{xa(i):.1f}" cy="{ya(a):.1f}" r="3" fill="#b0362d"/><text x="{xa(i):.1f}" y="{ya(a) - 6:.1f}" text-anchor="middle" class="lbl">{pct(a)}</text>')
        s.append(f'<text x="{xa(i):.1f}" y="{H - 6}" text-anchor="middle" class="lbl">手 {i}</text>')
    s.append(f'<text x="{L}" y="{H - 6}" class="lbl">赤＝欠航確率、薄い棒＝期待費用</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(s)}</svg>'


def year_bars(by_year: list[dict], W=520, H=120) -> str:
    L, R, T, B = 30, 10, 14, 22
    n = len(by_year); top = max(y.get("visits", 0) for y in by_year) or 1
    bw = (W - L - R) / n
    s = []
    for i, y in enumerate(by_year):
        v = y.get("visits", 0); h = v / top * (H - T - B)
        s.append(f'<rect x="{L + i * bw + 3:.1f}" y="{H - B - h:.1f}" width="{bw - 6:.1f}" height="{h:.1f}" fill="{"#7a5aa8" if y.get("retired") else "#274c77"}"/>')
        s.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{H - 6}" text-anchor="middle" class="lbl">{esc(str(y.get("year", y.get("fy", "")))[-4:])}</text>')
        s.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{H - B - h - 3:.1f}" text-anchor="middle" class="lbl">{v}</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="chart">{"".join(s)}</svg>'


# ---------------------------------------------------------------- sections
def table(head: list[str], rows: list[list], cls="") -> str:
    return f'<table class="{cls}"><thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in head)}</tr></thead><tbody>' + "".join(
        "<tr>" + "".join(f"<td>{x if isinstance(x, str) and x.startswith('<') else esc(x)}</td>" for x in r) + "</tr>" for r in rows) + "</tbody></table>"


def two(cs: list[dict], label: str, f) -> list:
    return [label] + [f(c) for c in cs]


def sec_conclusion(cs):
    rows = []
    for c in cs:
        for v in c["verdict"]:
            rows.append([c["name"], v["q"], v["a"], v["why"]])
    return "<h2>1. 結論</h2>" + table(["会社", "問い", "答え", "理由"], rows, "wide").replace("<table", '<table style="table-layout:fixed"', 1).replace("<thead>", "<colgroup><col style=\"width:16%\"><col style=\"width:9%\"><col style=\"width:33%\"><col style=\"width:42%\"></colgroup><thead>", 1)


def sec_demand(cs):
    def lf(c):
        d = c.get("demand"); return f'{d["carrier"]["lf_avg"] * 100:.1f}%' if d and d["carrier"].get("lf_avg") is not None else "—"
    def tight(c):
        d = c.get("demand"); return f'{len(d["carrier"]["tight_months"])} 月、満たせなかった需要 {d["carrier"]["spilled_rpk_total"] / 100:.1f} 億人キロ' if d else "—"
    def growth(c):
        p = c.get("plan_from_demand"); g = p and p["derived"]
        return f'直近 {g["demand_growth_per_year"] * 100:+.1f}%／長期 {g["demand_growth_long_run"] * 100:+.1f}%、稼働 ×{g["utilisation_multiplier"]:.3f}、引き金 {"引かれた" if g["review"]["triggered"] else "なし"}（{g["review"]["latest_yoy"]["m"]} 前年比 {g["review"]["latest_yoy"]["yoy"] * 100:+.1f}%）' if g else "—"
    def head(c):
        d = c.get("demand"); e = d and d.get("engines")
        return f'供給の {e["window"]["ask_headroom_share_avg"] * 100:.0f}%（足りない月 {e["window"]["short_months"]}）' if e else "—"
    def req(c):
        return f'便の計画が必要エンジン数を決める（{(c.get("growth") or {}).get("schedule_source", "—")}）。{c["verdict"][1]["a"]}'
    rows = [two(cs, "国内線の利用率（市場 A・社別 A/B）", lf), two(cs, "逼迫した月と溢れた需要（下限、C）", tight), two(cs, "需要から引いた前提", growth),
            two(cs, "エンジンの余力（客席換算）", head), two(cs, "必要エンジン数の根拠", req)]
    return "<h2>2. 需要と必要エンジン数（一つ上の層）</h2><p>出典：国土交通省 航空輸送統計速報（市場）、各社の月次資料（社別）。逼迫の閾値 85% は仮定。</p>" + table(["項目"] + [c["name"] for c in cs], rows, "wide")


def sec_basic(cs):
    out = "<h2>3. 基本計画（年次の版）</h2><p>年に 1 回、20 年先まで見て版を作る。MILP で 40 本のシナリオを同時に見て 1 つの計画を選び、その計画を 800 本の乱数世界で 24 か月ずつ叩く。</p>"
    for c in cs:
        f = c["fiscal_years"]; r = c.get("runout") or {}; tot = r.get("totals", {})
        out += f'<h3>{esc(c["name"])}</h3><div class="cols"><div>' + bars([(x["fy"], x["spend"] / 1000, x["budget"] / 1000) for x in f], unit="", fmt=lambda v: f"{v:,.1f}") + \
            '<p class="cap">年度ごとの整備費（百万ドル）。黒い線＝予算。赤＝予算超過。</p></div><div>' + \
            (year_bars(r["by_year"]) + '<p class="cap">退役までの入場（年ごとの件数）。紫＝退役のある年。</p>' if r.get("by_year") else "") + "</div></div>"
        out += table(["項目", "値"], [
            ["24 か月の入場", f'{sum(x["visits"] for x in f)} 件、整備費 {musd(sum(x["spend"] for x in f))} 百万ドル（予算 {musd(sum(x["budget"] for x in f))}）'],
            ["退役までの入場列", f'{tot.get("visits", "—")} 件、{musd(tot.get("spend_k", 0))} 百万ドル、寿命を残して退役 {tot.get("green_time_engines", "—")} 基（残存価値 {musd(tot.get("residual_value_k", 0))} 百万ドル）、空の年の理由＝退役が入場を吸う'] if tot else ["退役までの入場列", "—"],
            ["受領遅れ（置き換え機）", (lambda dd: f'6 か月遅れで入場 +{dd["6"]["extra_visits"]} 件・{musd(dd["6"]["extra_spend_k"])} 百万ドル、知っていれば +{dd["6"]["known"]["extra_visits"]} 件・{musd(dd["6"]["known"]["extra_spend_k"])}' if dd and "6" in dd else "—")(r.get("delivery_delay"))],
            ["運航側の最薄月", (lambda o: f'{o["thin"]["label"]}（余力 {o["thin"]["margin"]:+d} 基）、足りない月 {o["months_short"]}' if o else "—")(r.get("ops_summary"))],
        ])
    return out


def sec_purchase(cs):
    out = "<h2>4. 購入計画の輪（1 手ずつ足して解き直す）</h2><p>候補（予備リース・購入・プール・中寿命機への入れ替え）をそれぞれ試し、欠航 1 点あたり最も安い手を 1 つ足す。欠航確率が 5% を切るまで繰り返す。上限：中寿命機は 2 年で 4 基（中古市場、仮定）、プール 3 基。</p>"
    for c in cs:
        P = c.get("purchase")
        if not P:
            continue
        s = P["summary"]
        out += f'<h3>{esc(c["name"])}</h3><div class="cols"><div>' + line_steps(P["trajectory"]) + "</div><div>" + table(["手", "足したもの", "欠航", "費用（百万ドル）"], [
            [t["step"], t["added"]["label"] if t["added"] else "今の機隊", pct(t["expected"]["aog_prob"]), musd(t["expected"]["total_cost"])] for t in P["trajectory"]]) + "</div></div>"
        out += table(["購入計画", "基数", "発注", "使える月"], [[f'{p.get("what", "")}（{p.get("note", "")}）', p.get("count", ""), p.get("order_by", ""), p.get("in_service", "")] for p in P["purchase_plan"]]) if P.get("purchase_plan") else ""
        out += f'<p>結果：欠航 {pct(s["aog_before"])} → {pct(s["aog_after"])}、費用 {musd(s["cost_before"])} → {musd(s["cost_after"])} 百万ドル（{s["steps"]} 手、{"目標到達" if s["reached"] else "上限で停止"}）。</p>'
        out += "<ul>" + "".join(f'<li><b>{esc(k.get("kind", ""))}</b>：{esc(k.get("text", ""))}</li>' for k in P.get("couplings", [])) + "</ul>"
        out += f'<p class="cap">戻りの輪：月次＝{esc(P["feedback"]["monthly"])}。年次＝{esc(P["feedback"]["yearly"])}。</p>'
    return out


def sec_playbook(cs):
    out = "<h2>5. 打ち手の順番（キット → 契約 → 第二工場の選択権）</h2>"
    for c in cs:
        P = c.get("playbook")
        if not P:
            continue
        out += f'<h3>{esc(c["name"])}</h3><ul>' + "".join(f'<li><b>[{v["status"]}]</b> {esc(v["text"])}</li>' for v in P["verdict"]) + "</ul>"
        out += f'<p>ループの時間 {P["loop_time"]["before"]:.0f} → {P["loop_time"]["after"]:.0f} か月。期待節減 {musd(P["summary"]["expected_saving_k"])} 百万ドル、欠航 {P["summary"]["aog_delta_pt"]:+.1f}pt。</p>'
    return out


def sec_detail(cs):
    out = "<h2>6. 詳細計画（月次〜当日）</h2><p>月ごとに実績を入れ、世界の確率を更新し、3 か月先の不足を見張る。見張りが引いたら年次を待たずに購入の輪を回す。</p>"
    rows = []
    for c in cs:
        t = c.get("track") or {}; sh = c.get("shortage") or {}; rv = c.get("review") or {}
        top = [s for s in rv.get("symptoms", []) if s["severity"] in ("crit", "warn")][:4]
        rows.append([c["name"],
                     f'{esc(t.get("world", "—"))} {pct(t.get("world_p", 0))}、計画との一致 {pct(t.get("follow", 0), 0)}、例外 {t.get("exceptions", "—")} 件、{ {"switch": "乗り換えを推奨", "stay": "今の計画を続ける"}.get(t.get("recommend"), t.get("recommend", "—")) }',
                     f'{sh.get("as_of", "—")}：最悪月 {sh.get("worst", {}).get("label", "—")}、欠航確率 {pct(sh.get("worst", {}).get("p_aog", 0))}、{"引かれた → " + esc(sh.get("fix", {}).get("what", "")) if sh.get("triggered") else "引かれず（" + esc(sh.get("fix", {}).get("what", "")) + "）"}' if sh else "—",
                     "<ul>" + "".join(f'<li>[{s["stage"]}・{s["severity"]}] {esc(s["finding"])}</li>' for s in top) + "</ul>"])
    return out + table(["会社", "追跡（世界の確率・一致・例外）", "不足の見張り", "見直しの症状（上位）"], rows, "wide")


def sec_verify(cs):
    out = "<h2>7. 検証（過去で当てる）</h2><p>過去 14 版を当時の情報で解き直し、学ぶ 5 版／確かめる 5 版に分けて補正の効きを採点する（最初の 5 年は捨てる）。</p>"
    rows = []
    for c in cs:
        b = (c.get("backtest") or {}).get("engine") or {}
        tm = b.get("timing", {})
        rows.append([c["name"], f'{b.get("n_versions", "—")} 版・被覆率 {pct(b.get("coverage", 0), 0)}', f'{tm.get("mean", 0):+.1f} か月（sd {tm.get("sd", 0):.1f}）' if tm else "—",
                     f'件数比 {b.get("volume_ratio", 0):.2f}、費用比 {b.get("spend_ratio", 0):.2f}、計画外比 {b.get("unsched_ratio", 0):.2f}',
                     "<ul>" + "".join(f'<li>{esc(v.get("text", v))}</li>' for v in b.get("verdict", [])[:4]) + "</ul>"])
    out += table(["会社", "版と被覆率", "入場時期のずれ", "件数・費用・計画外", "判定"], rows, "wide")
    d = [(c["name"], (c.get("backtest") or {}).get("demand")) for c in cs]
    out += "<h3>需要の伸びの決め方</h3><ul>" + "".join(f'<li>{esc(n)}：' + "；".join(esc(v.get("text", v)) for v in (x or {}).get("verdict", [])) + "</li>" for n, x in d) + "</ul>"
    return out


def sec_next():
    return "<h2>8. 次の版で直す 3 点</h2><ol><li>需要の伸びの既定を長期寄りに（直近の傾向は引き金の材料に格下げ）。実データの検証で長期が勝った。</li><li>入場の期限を +1〜2 か月後ろへ（予測が保守的）。学ぶ・確かめるの外の区間でも効いた。</li><li>計画外取卸しの率は上方修正の候補だが、確かめる期間では件数の予測を悪くした。次の版では学ぶ期間を伸ばして再判定する。</li></ol><p>構造：エンジン 1 基の入場 → 2 年の計画 → 退役までの列 → 機材の移行 → 路線と客席の需要 → 会社の戦略。上の層が下の層の「必要」を決め、下の層は上の層に「余力」と「限界」を返す。</p>"


def appendix_a(fig: dict) -> str:
    loops = table(["輪", "何を", "回数", "回す条件", "段階", "頁"], [list(r[:6]) for r in figures.LOOPS], "small")
    hand = table(["向き", "何が", "どこへ"], [list(r) for r in figures.HANDOVER], "small")
    return ('<h2 class="appendix">付録 A. 思考の枠組み：基本計画は PDCA、詳細計画は OODA</h2><p>本文の裏で使っている考え方。行は業務プロセス、列は時間の段階。深紅の枠＝繰り返し（タブに名前・回数・条件）、藍の点線枠＝内側の 1 回、青緑の札＝頁をまたぐ受け渡し。二つの輪は互いの入力：OODA の Observe（実績）と Orient（事後確率・変化点）は次の版の Plan の入力、Plan の出力（基準計画）は Orient の入力。</p>'
            + loops + "<h3>頁をまたぐ受け渡し</h3>" + hand
            + halves("図 A-1　P1 基本計画（年次〜半期、PDCA）", fig["plan_basic"]) + halves("図 A-2　P2 詳細計画（月次〜当日、OODA）", fig["plan_detail"]))


def halves(title: str, svg: str) -> str:
    """One figure on two A4 landscape pages: the upper three process rows, then the lower three
    with the legend. The frames that span both halves are cut at the boundary on purpose."""
    import re
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    W, Hh = int(vb.group(1)), int(vb.group(2))
    cut = 130 + 3 * (Hh - 130 - 176) / 6  # top of the fourth process row (Page.T and Page.rh in figures.py)
    top = svg.replace(vb.group(0), f'viewBox="0 0 {W} {cut:.0f}"', 1)
    bot = svg.replace(vb.group(0), f'viewBox="0 {cut:.0f} {W} {Hh - cut:.0f}"', 1)
    return (f'<section class="land"><h3>{esc(title)}　（上段：経営・整備計画・調達）</h3><div class="fig">{top}</div></section>'
            f'<section class="land"><h3>{esc(title)}　（下段：運航・技術・財務、凡例）</h3><div class="fig">{bot}</div></section>')


def appendix_md() -> str:
    md = (HERE / "handover" / "04_docs" / "appendix_思考の枠組み.md").read_text(encoding="utf-8")
    # sections B and C of the appendix document (A is drawn above)
    body = md.split("## B. ")[1]
    b, c = body.split("## C. ")
    def inner(t: str) -> str:
        h = bd.md_to_html("## " + t, "")
        h = h.split("<main>")[1].split("</main>")[0]
        return h.replace('<p class="top"><a href="index.html">← ダッシュボード</a></p>', "", 1).replace("<h2>", "<h2>付録 ", 1).replace("<h3>", "<h3>", 1)
    figb = ('<figure style="margin:6pt 0"><div style="border:1px solid #d3dbe3;border-radius:6px;background:#fbfbfd">' + figures.strategy_matrix(False) + '</div><figcaption class="cap">図 B-1　あるべき分析ストラテジー：層 × 流れ。行＝層（観測が上がり、決定が下りる）、列＝入る → 回す → 出る、右端＝あるべき結果。深紅の枠＝新しく足す層、太い深紅＝推奨の経路。重ね（航空計画から導くもの・PDCA／OODA の段階・成果指標・何が働くか）は HTML 版 strategy_concept.html で一つずつ見る。</figcaption></figure>'
            '<figure style="margin:6pt 0"><div style="border:1px solid #d3dbe3;border-radius:6px;background:#fbfbfd">' + figures.strategy_stack() + '</div><figcaption class="cap">図 B-2　同じ内容を流れだけで：観測 → 4 つのストラテジー → 束ねる → 計画を解く → あるべき結果。</figcaption></figure>')
    hb = inner("B. " + b)
    k = hb.find("<h3>")  # the figure goes right after the section's opening paragraph, before B-1
    return (hb[:k] + figb + hb[k:] if k > 0 else hb + figb) + inner("C. " + c)


def appendix_e() -> str:
    rows = decisions.rows_html(esc)
    opt = "、".join(f"{esc(l)}（{esc(f)}）" for f, l in decisions.OPTIONAL_SCREENS)
    return ('<h2>付録 E. 意思決定レポートとシミュレーション画面の対応</h2><p>この A4 版は「何を決めるか」を書く意思決定レポート。判断材料はシミュレーション画面（対話版 report.html と月次・年次・追跡の画面）に置き、別に出せる。'
            '下の表が、分析結果 → 判断材料 → 画面 → 本文の章 → 誰がいつ決めるか、の対応。</p>'
            f'<table class="small"><thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in decisions.HEAD)}</tr></thead><tbody>{rows}</tbody></table>'
            f'<p class="cap">画面の列は対話版レポートの画面名（report.html）、または別画面（annual／monthly／track）。任意で足せる画面：{opt}。</p>')


def appendix_d(cs):
    rows = []
    for c in cs:
        rows.append([c["name"], len(c["unsourced"]), "、".join(esc(u["where"]) for u in c["unsourced"][:12]) + ("…" if len(c["unsourced"]) > 12 else "")])
    return "<h2>付録 D. 前提と出典</h2><p>実データは出典と確からしさ（A：一次統計、B：報道の再掲、C：仮定）を付けている。出典のない数字は「出典なし」と印を付け、ここに数を出す。</p>" + table(["会社", "出典のない数字", "どこ"], rows, "wide") + \
        "<p>すべての数値は合成データ（機材・工場・契約は実在の会社に似せた架空の値）。実データは需要（e-Stat 航空輸送統計速報、各社月次資料）と型式の年表のみ。</p>"


CSS = """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; @bottom-center { content: counter(page); font-size: 9pt; color: #5b6a78; } }
@page land { size: A4 landscape; margin: 10mm; }
html { font-family: "IBM Plex Sans JP", "Noto Sans JP", "Hiragino Sans", sans-serif; color: #13202c; font-size: 10.5pt; line-height: 1.55; }
body { margin: 0; }
.sheet { max-width: 182mm; margin: 0 auto; padding: 8mm 0; }
h1 { font-size: 22pt; margin: 0 0 4pt; } h2 { font-size: 14pt; margin: 18pt 0 6pt; border-bottom: 2px solid #274c77; padding-bottom: 2pt; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; page-break-after: avoid; } p { margin: 4pt 0; } ul, ol { margin: 4pt 0 4pt 16pt; padding: 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 4pt 0 8pt; page-break-inside: auto; } th, td { border: 1px solid #d3dbe3; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #eef2f5; } tr { page-break-inside: avoid; } table.small { font-size: 8pt; } td ul { margin: 0 0 0 12pt; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; align-items: start; } .chart { width: 100%; height: auto; } .chart text, .chart .lbl { font-size: 13px; fill: #5b6a78; font-family: inherit; }
.cap { font-size: 8.5pt; color: #5b6a78; } .cover { min-height: 240mm; display: flex; flex-direction: column; justify-content: center; }
.cover .tag { color: #5b6a78; letter-spacing: .2em; font-size: 9pt; } .cover .sub { font-size: 13pt; margin-top: 8pt; } .cover .meta { margin-top: 40pt; font-size: 9.5pt; color: #5b6a78; }
.toc li { margin: 2pt 0; } .note { background: #f6e8d3; border-left: 3px solid #a8671a; padding: 4pt 8pt; font-size: 9pt; }
section.land { page: land; page-break-before: always; page-break-after: always; } .land .fig svg { width: 272mm; height: auto; display: block; } .land h3 { margin: 0 0 2mm; font-size: 10.5pt; }
.cover { page-break-after: always; } h2.appendix { page-break-before: always; }
@media screen { body { background: #eef2f5; } .sheet { background: #fff; padding: 14mm; box-shadow: 0 2px 12px rgba(0,0,0,.12); margin: 12mm auto; } section.land { max-width: 277mm; overflow: auto; } }
"""


def build_html(cs: list[dict], today: str) -> str:
    fig = figures.svgs()
    toc = ["1. 結論", "2. 需要と必要エンジン数", "3. 基本計画（年次の版）", "4. 購入計画の輪", "5. 打ち手の順番", "6. 詳細計画（月次〜当日）", "7. 検証（過去で当てる）", "8. 次の版で直す 3 点",
           "付録 A. 思考の枠組み（PDCA／OODA、2 頁の図）", "付録 B. 新しい情報の重みづけ（文献）", "付録 C. シミュレーションの範囲（矢印の包含）", "付録 D. 前提と出典", "付録 E. 意思決定レポートとシミュレーション画面の対応"]
    cover = f'<div class="cover"><div class="tag">737-800 / CFM56-7B　エンジン整備計画</div><h1>エンジン整備計画レポート</h1><div class="sub">需要から検証まで：基本計画（年次）と詳細計画（月次）、購入計画の輪、過去での検証</div>' \
            f'<div class="meta">{today} 版　　対象：{"、".join(esc(c["name"]) for c in cs)}<br>Aether Platform 上のエンジン計画コンポーネント（Secretary.io が会議と版をつなぐ）<br><b>すべて合成データ</b>。実データは需要と型式の年表のみ、出典と確からしさを付記。</div>' \
            f'<h3 style="margin-top:32pt">目次</h3><ul class="toc">{"".join(f"<li>{esc(t)}</li>" for t in toc)}</ul></div>'
    body = sec_conclusion(cs).replace("<h2>", '<h2 class="first">', 1).replace("</table>", '</table><p class="cap">判断材料はシミュレーション画面にある（付録 E に対応表）。この文書は決めることと理由だけを書く。</p>', 1) + sec_demand(cs) + sec_basic(cs) + sec_purchase(cs) + sec_playbook(cs) + sec_detail(cs) + sec_verify(cs) + sec_next() \
        + appendix_a(fig) + appendix_md() + appendix_d(cs) + appendix_e()
    return f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>エンジン整備計画レポート（A4）</title><style>{CSS}</style></head><body><div class="sheet">{cover}{body}<p class="cap">生成：build_a4.py（{today}）。対話版のレポート（report.html）が明細、この A4 版が本文。</p></div></body></html>'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=Path("out"))
    ap.add_argument("--html-out", type=Path)
    ap.add_argument("--pdf", type=Path, help="also render this PDF with Chromium (playwright)")
    a = ap.parse_args(argv)
    html_out = a.html_out or a.out_dir / "report_a4.html"
    cs = [company_bundle(a.out_dir, c) for c in COS]
    html_out.write_text(build_html(cs, date.today().isoformat()), encoding="utf-8")
    print(f"a4 -> {html_out} ({html_out.stat().st_size // 1024} KB)")
    if a.pdf:
        from playwright.sync_api import sync_playwright
        import os
        exe = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=exe) if Path(exe).exists() else p.chromium.launch()
            pg = b.new_page(); pg.goto(html_out.resolve().as_uri()); pg.wait_for_timeout(500); pg.emulate_media(media="print")
            pg.pdf(path=str(a.pdf), format="A4", print_background=True, prefer_css_page_size=True, display_header_footer=False)
            b.close()
        print(f"pdf -> {a.pdf} ({a.pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
