#!/usr/bin/env python3
"""The route capacity optimization drawn: what is chosen, who answers, and what is maximized.

  1. structure   premises -> the upper level's plan (route x company x 0/2/4) -> each company's
                 fleet assignment -> each plan's results -> the six objectives, the best plan of
                 each fed back to the top
  2. plans       (when fleet/route_opt/*.json exist) the 729 plans of each world on company A's
                 change in margin x company B's, the quadrant where no one loses shaded, each
                 objective's best plan marked; and a table of the best plans

Colors: the five quantities a plan produces take the reference categorical palette in fixed order
(validated: scripts/validate_palette.js, all checks pass; three slots below 3:1 on the surface, so
every chip carries its text label). Text stays in ink.

  python fig_route_opt.py      # handover/03_reports/route_opt.html
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from figures import tw

HERE = Path(__file__).resolve().parent
OUT = HERE / "handover" / "03_reports" / "route_opt.html"
OPT = HERE / "fleet" / "route_opt"

SURF = "#fcfcfb"; PAGE = "#f9f9f7"; INK = "#0b0b0b"; INK2 = "#52514e"; MUTE = "#898781"; GRID = "#e1e0d9"; AXIS = "#c3c2b7"
NAVY = "#1c5cab"
Q = {"pax": ("#e87ba4", "新しい旅客"), "surplus": ("#1baf7a", "利用者の得（運賃 × 0.45）"), "a": ("#2a78d6", "会社 A の差し引き"),
     "b": ("#eb6834", "会社 B の差し引き"), "cost": ("#eda100", "空港の年の費用")}
OBJ = [("welfare", "社会の得", "国・利用者", [("+", "surplus"), ("+", "a"), ("+", "b"), ("−", "cost")], None),
       ("welfare_ok", "誰も損しない社会の得", "国（埋め合わせなし）", [("+", "surplus"), ("+", "a"), ("+", "b"), ("−", "cost")], "条件：会社 A ≥ 0、会社 B ≥ 0"),
       ("joint", "業界の得", "二社の合計", [("+", "a"), ("+", "b")], None),
       ("a", "会社 A の得", "会社 A", [("+", "a")], None),
       ("b", "会社 B の得", "会社 B", [("+", "b")], None),
       ("pax_per_cost", "1 億円あたりの旅客", "空港（前の順番の物差し）", [("", "pax"), ("÷", "capital")], None)]
WNAME = {"before": "リニアの前", "after_66_rule": "リニアの後（配分の規則の世界）"}
FNAME = {"distance": "運賃は距離だけ", "fitted": "運賃を搭乗率に合わせる"}
APT = {"CTS": "新千歳", "FUK": "福岡", "OKA": "那覇"}


def t(x, y, s, size=12, w=400, fill=INK, anchor="start"):
    return f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}">{html.escape(s)}</text>'


def box(x, y, w, h, fill="#ffffff", stroke=AXIS, rx=8, sw=1.2):
    return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def chip(x, y, key, size=12, label=None):
    """A labeled quantity: a colored dot and its name. Returns (svg, width)."""
    col, name = Q[key] if key in Q else (MUTE, "空港の事業費")
    name = label or name
    w = tw(name, size) + 30
    return (box(x, y, w, 24, fill="#ffffff", stroke=col, rx=12, sw=2) + f'<circle cx="{x + 12:.0f}" cy="{y + 12:.0f}" r="5" fill="{col}"/>'
            + t(x + 22, y + 16.5, name, size)), w


def arrow(x1, y1, x2, y2, col=INK2, label=None):
    s = f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{col}" stroke-width="2" marker-end="url(#ah)"/>'
    if label:
        s += t((x1 + x2) / 2 + 10, (y1 + y2) / 2 + 4, label, 11.5, fill=INK2)
    return s


def structure(winners: dict | None = None) -> str:
    W, H = 1240, 1010
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="路線の容量の最適化の構造" font-family="IBM Plex Sans JP, system-ui, sans-serif">',
         f'<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto-start-reverse"><path d="M0,0 L9,4.5 L0,9 z" fill="{INK2}"/></marker></defs>',
         box(0, 0, W, H, fill=SURF, stroke=SURF, rx=0)]
    # 1. premises
    o.append(box(20, 16, 1160, 74, fill=PAGE))
    o.append(t(36, 40, "前提（経営と政治が決める）", 14, 700))
    x = 36
    for s in ("リニア：羽田–伊丹の航空に 66% 残る", "空いた伊丹の枠は他の幹線に移さない（配分の規則）", "炭素：排出量取引の帯（〜1 万円/t）", "需要：今の伸びのまま"):
        w = tw(s, 12) + 20
        o.append(box(x, 52, w, 26, fill="#ffffff", rx=13) + t(x + 10, 69.5, s, 12, fill=INK2)); x += w + 10
    o.append(arrow(600, 92, 600, 116))
    # 2. upper level
    o.append(box(20, 118, 1160, 196, stroke=NAVY, sw=1.6))
    o.append(t(36, 144, "上の段：政府・空港が選ぶ（決める変数）", 15, 700))
    o.append(t(36, 166, "路線ごと・会社ごとに、1 日に足す往復の数", 12, fill=INK2))
    gx, gy, cw, rh = 60, 182, 150, 34
    o.append(t(gx + 110 + cw / 2, gy + 14, "会社 A", 12, 700, anchor="middle") + t(gx + 110 + cw * 1.5, gy + 14, "会社 B", 12, 700, anchor="middle"))
    for i, a in enumerate(("新千歳", "福岡", "那覇")):
        y = gy + 22 + i * rh
        o.append(t(gx, y + 21, a, 12, 700))
        for j in range(2):
            o.append(box(gx + 110 + j * cw + 6, y + 4, cw - 12, rh - 8, fill=PAGE, rx=6) + t(gx + 110 + j * cw + cw / 2, y + 22, "0 ・ 2 ・ 4", 12, anchor="middle"))
    o.append(t(520, 214, "3 路線 × 2 社 × 3 通り ＝ 3⁶ ＝ 729 の計画", 14, 700))
    o.append(t(520, 238, "他の航空会社には、両社の合計の取り分を保つ分を足す（便数だけ動く）", 12, fill=INK2))
    o.append(t(520, 260, "空港の事業費 ＝ 足した往復 ×（羽田 34 ＋ 対向空港 25〜50 億円 / 1 日 1 往復）", 12, fill=INK2))
    o.append(t(520, 282, "729 通りをすべて解く → 目的ごとに、格子の上で厳密な最良", 12, 700, fill=NAVY))
    # 3. lower level
    o.append(arrow(340, 316, 340, 342, label="計画を渡す") + arrow(860, 316, 860, 342))
    for k, (x, name, other) in enumerate(((20, "会社 A", "会社 B"), (620, "会社 B", "会社 A"))):
        o.append(box(x, 344, 560, 150, stroke=NAVY, sw=1.6))
        o.append(t(x + 16, 370, f"下の段：{name}の機材割当（混合整数計画、月ごと）", 14, 700))
        o.append(t(x + 16, 394, "最小化：運航費 ＋ 737 のリース ＋ 乗せられない旅客の売上", 12))
        o.append(t(x + 16, 416, "制約：羽田の枠・対向空港の上限・機数（整備で抜ける分を引く）", 12, fill=INK2))
        o.append(t(x + 16, 438, "需要：便数の比率で取り分、便ごとのばらつき（取りこぼし）", 12, fill=INK2))
        o.append(t(x + 16, 460, f"{other}の足した便は競争相手の便として入る", 12, fill=INK2))
        o.append(t(x + 16, 482, "運賃は据え置き", 12, fill=INK2))
    o.append(f'<line x1="582" y1="420" x2="618" y2="420" stroke="{INK2}" stroke-width="2" marker-end="url(#ah)" marker-start="url(#ah)"/>')
    # 4. results
    o.append(arrow(340, 496, 340, 522) + arrow(860, 496, 860, 522))
    o.append(box(20, 524, 1160, 108, fill=PAGE))
    o.append(t(36, 548, "計画ごとの結果（今の便数との差、FY2030、年）", 14, 700))
    x = 36
    for key in ("pax", "surplus", "a", "b", "cost"):
        s, w = chip(x, 560, key); o.append(s); x += w + 10
    o.append(t(36, 614, "返りとして見るもの（目的には入れない）：機材の組み合わせ・エンジンの傷み方と整備費・CO2", 12, fill=INK2))
    # 5. objectives
    o.append(arrow(600, 634, 600, 660))
    o.append(t(20, 680, "目的：どれを最大にするか（6 通り。どれを選ぶかが政策の判断）", 15, 700))
    cw2, ch = 380, 140
    for i, (key, title, who, terms, cond) in enumerate(OBJ):
        x = 20 + (i % 3) * (cw2 + 10); y = 692 + (i // 3) * (ch + 12)
        o.append(box(x, y, cw2, ch))
        o.append(t(x + 14, y + 24, title, 14, 700) + t(x + cw2 - 14, y + 24, who, 11.5, fill=INK2, anchor="end"))
        cx, cy = x + 14, y + 38
        for n, (op, k) in enumerate(terms):
            if op and not (n == 0 and op == "+"):
                o.append(t(cx + 6, cy + 17, op, 14, 700)); cx += 20
            lab = None
            short = {"surplus": "利用者の得", "a": "会社 A", "b": "会社 B", "cost": "空港の年の費用", "pax": "新しい旅客", "capital": "空港の事業費"}[k]
            s, w = chip(cx, cy, k, 11.5, short)
            if cx + w > x + cw2 - 10:
                cx, cy = x + 14, cy + 30
                s, w = chip(cx, cy, k, 11.5, short)
            o.append(s); cx += w + 4
        if cond:
            o.append(t(x + 14, y + 104, cond, 12, 700, fill=NAVY))
        if winners and winners.get(key):
            o.append(t(x + 14, y + ch - 12, "最良：" + winners[key], 11.5, fill=INK2))
    # feedback
    o.append(f'<path d="M1182,760 L1204,760 L1204,214 L1184,214" fill="none" stroke="{NAVY}" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#ah)"/>')
    o.append(f'<text x="1222" y="490" font-size="12" font-weight="700" fill="{NAVY}" transform="rotate(90 1222 490)" text-anchor="middle">729 の中で最大の計画を選ぶ</text>')
    o.append("</svg>")
    return "".join(o)


def plan_text(p: dict) -> str:
    parts = []
    for code in ("CTS", "FUK", "OKA"):
        a, b = p["jal"].get(code, 0), p["ana"].get(code, 0)
        if a or b:
            parts.append(f"{APT[code]} A+{a}・B+{b}")
    return "、".join(parts) or "足さない"


MARK = {"welfare_mid": ("社会", "circle"), "welfare_ok_mid": ("誰も損しない", "square"), "joint": ("業界", "diamond"),
        "a": ("A", "tri"), "b": ("B", "tri_down"), "pax_per_cost": ("空港", "cross")}


def shape(kind, x, y, r=7):
    st = f'fill="none" stroke="{INK}" stroke-width="2"'
    if kind == "circle":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" {st}/>'
    if kind == "square":
        return f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r}" height="{2 * r}" {st}/>'
    if kind == "diamond":
        return f'<path d="M{x:.1f},{y - r - 2:.1f} L{x + r + 2:.1f},{y:.1f} L{x:.1f},{y + r + 2:.1f} L{x - r - 2:.1f},{y:.1f} z" {st}/>'
    if kind == "tri":
        return f'<path d="M{x:.1f},{y - r - 1:.1f} L{x + r + 1:.1f},{y + r:.1f} L{x - r - 1:.1f},{y + r:.1f} z" {st}/>'
    if kind == "tri_down":
        return f'<path d="M{x:.1f},{y + r + 1:.1f} L{x + r + 1:.1f},{y - r:.1f} L{x - r - 1:.1f},{y - r:.1f} z" {st}/>'
    return f'<path d="M{x - r:.1f},{y - r:.1f} L{x + r:.1f},{y + r:.1f} M{x + r:.1f},{y - r:.1f} L{x - r:.1f},{y + r:.1f}" stroke="{INK}" stroke-width="2.4"/>'


def scatter(rows: list[dict], best: dict, title: str) -> str:
    W, H, L, R, T, B = 560, 400, 58, 16, 40, 46
    xs = [r["margin_change_oku"]["jal"] for r in rows]; ys = [r["margin_change_oku"]["ana"] for r in rows]
    x0, x1 = min(xs + [0]) - 5, max(xs + [0]) + 5; y0, y1 = min(ys + [0]) - 5, max(ys + [0]) + 5
    X = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)  # noqa: E731
    Y = lambda v: H - B - (v - y0) / (y1 - y0) * (H - T - B)  # noqa: E731
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" font-family="IBM Plex Sans JP, system-ui, sans-serif">', box(0, 0, W, H, fill=SURF, stroke=GRID)]
    o.append(t(14, 24, title, 13, 700))
    o.append(f'<rect x="{X(0):.1f}" y="{T}" width="{W - R - X(0):.1f}" height="{Y(0) - T:.1f}" fill="#1baf7a" fill-opacity="0.10"/>')
    o.append(t(W - R - 6, T + 16, "誰も損しない", 11.5, fill=INK2, anchor="end"))
    step = 20 if (x1 - x0) < 160 else 40
    v = (int(x0 // step) + 1) * step
    while v < x1:
        o.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{H - B}" stroke="{GRID}"/>' + t(X(v), H - B + 16, f"{v:+d}" if v else "0", 11, fill=MUTE, anchor="middle")); v += step
    step = 20 if (y1 - y0) < 160 else 40
    v = (int(y0 // step) + 1) * step
    while v < y1:
        o.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{W - R}" y2="{Y(v):.1f}" stroke="{GRID}"/>' + t(L - 6, Y(v) + 4, f"{v:+d}" if v else "0", 11, fill=MUTE, anchor="end")); v += step
    o.append(f'<line x1="{X(0):.1f}" y1="{T}" x2="{X(0):.1f}" y2="{H - B}" stroke="{AXIS}" stroke-width="1.5"/><line x1="{L}" y1="{Y(0):.1f}" x2="{W - R}" y2="{Y(0):.1f}" stroke="{AXIS}" stroke-width="1.5"/>')
    o.append(t((L + W - R) / 2, H - 10, "会社 A の差し引きの変化（億円/年）", 11.5, fill=INK2, anchor="middle"))
    o.append(f'<text x="14" y="{(T + H - B) / 2:.0f}" font-size="11.5" fill="{INK2}" text-anchor="middle" transform="rotate(-90 14 {(T + H - B) / 2:.0f})">会社 B の差し引きの変化（億円/年）</text>')
    for r in rows:
        tip = f'{plan_text(r["plan"])}：A {r["margin_change_oku"]["jal"]:+.1f}・B {r["margin_change_oku"]["ana"]:+.1f} 億円、新しい旅客 {r["new_pax_k"]:.0f} 千人、空港 年 {r["annual_cost_oku"]:.1f} 億円'
        o.append(f'<circle cx="{X(r["margin_change_oku"]["jal"]):.1f}" cy="{Y(r["margin_change_oku"]["ana"]):.1f}" r="3" fill="{NAVY}" fill-opacity="0.35"><title>{html.escape(tip)}</title></circle>')
    placed = []
    for k, (lab, kind) in MARK.items():
        b = best.get(k)
        if not b:
            continue
        px, py = X(b["margin_change_oku"]["jal"]), Y(b["margin_change_oku"]["ana"])
        tip = f'{lab}：{plan_text(b["plan"])}'
        o.append(f'<g><title>{html.escape(tip)}</title>{shape(kind, px, py)}</g>')
        ly = py - 12
        while any(abs(ly - q[1]) < 13 and abs(px - q[0]) < 80 for q in placed):
            ly -= 13
        placed.append((px, ly))
        anchor = "end" if px > W - 120 else "start"
        o.append(t(px + (-10 if anchor == "end" else 10), ly, lab, 11.5, 700, anchor=anchor))
    o.append("</svg>")
    return "".join(o)


def results() -> tuple[str, dict]:
    s = json.loads((HERE / "fleet" / "route_opt_jal.json").read_text(encoding="utf-8")) if (HERE / "fleet" / "route_opt_jal.json").exists() else None
    if not s:
        return "", {}
    panels, rows_html, winners = [], [], {}
    for key, res in s["results"].items():
        world, fares = key.split("/")
        g = json.loads((OPT / f"{world}_{fares}.json").read_text(encoding="utf-8"))
        best = res["best"]
        panels.append(f'<figure>{scatter(g["rows"], best, WNAME[world] + "・" + FNAME[fares])}</figure>')
        for k, (lab, _) in MARK.items():
            b = best.get(k)
            if not b:
                rows_html.append(f"<tr><td>{WNAME[world]}・{FNAME[fares]}</td><td>{lab}</td><td colspan='6'>該当なし</td></tr>"); continue
            rows_html.append(f"<tr><td>{WNAME[world]}・{FNAME[fares]}</td><td>{lab}</td><td>{html.escape(plan_text(b['plan']))}</td><td>{b['new_pax_k']:.0f}</td>"
                             f"<td>{b['margin_change_oku']['jal']:+.1f}</td><td>{b['margin_change_oku']['ana']:+.1f}</td><td>{b['annual_cost_oku']:.1f}</td><td>{b['welfare_oku']:+.1f}</td></tr>")
        if world == "after_66_rule" and fares == "distance":
            winners = {"welfare": plan_text(best["welfare_mid"]["plan"]), "welfare_ok": plan_text(best["welfare_ok_mid"]["plan"]) if best.get("welfare_ok_mid") else "該当なし",
                       "joint": plan_text(best["joint"]["plan"]), "a": plan_text(best["a"]["plan"]), "b": plan_text(best["b"]["plan"]), "pax_per_cost": plan_text(best["pax_per_cost"]["plan"])}
    legend = "　".join(f"{lab}（{ {'circle': '○', 'square': '□', 'diamond': '◇', 'tri': '△', 'tri_down': '▽', 'cross': '×'}[kind] }）" for lab, kind in MARK.values())
    part = (f'<h2>2. 729 の計画と、目的ごとの最良</h2><p>点は 1 つの計画（会社 A と会社 B の差し引きの変化）。緑の帯は、どちらの会社も今より損をしない計画。印は目的ごとの最良：{legend}。点に重ねると計画の中身が出る。社会の得は利用者の得の割合 0.45。</p>'
            f'<div class="grid">{"".join(panels)}</div>'
            '<h2>表：目的ごとの最良の計画</h2><table><thead><tr><th>世界・運賃</th><th>目的</th><th>計画（足す往復/日）</th><th>新しい旅客（千人/年）</th><th>会社 A（億円/年）</th><th>会社 B（億円/年）</th><th>空港の年の費用（億円）</th><th>社会の得（億円/年）</th></tr></thead><tbody>'
            + "".join(rows_html) + "</tbody></table>")
    return part, winners


def page() -> str:
    part, winners = results()
    css = (f":root{{color-scheme:light}}body{{margin:0;background:{PAGE};color:{INK};font-family:'IBM Plex Sans JP',system-ui,sans-serif}}"
           "main{max-width:1240px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 6px}h2{font-size:16px;margin:28px 0 6px}"
           f"p{{font-size:13px;color:{INK2};margin:0 0 10px;line-height:1.6}}svg{{width:100%;height:auto;display:block}}figure{{margin:0}}"
           ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:12px}"
           f"table{{border-collapse:collapse;font-size:12.5px;width:100%;background:{SURF}}}th,td{{border-bottom:1px solid {GRID};padding:6px 8px;text-align:left;vertical-align:top}}"
           "td:nth-child(n+4),th:nth-child(n+4){text-align:right;font-variant-numeric:tabular-nums}.wrap{overflow-x:auto}")
    note = ("<p>上の段（政府・空港）が路線ごと・会社ごとに足す往復を選び、下の段（各社）が自社の機材割当で応じる二段の最適化。"
            "上の段は 729 通りをすべて解くので、格子の上では厳密。何を最大にするか（目的）で、選ばれる計画が変わる。"
            "数値は合成データと公開値の混合（`route_optimize.py`、`fleet/route_opt_jal.json`）。</p>")
    body = f"<h1>路線の容量の最適化：何を選び、誰が応じ、何を最大にするか</h1>{note}<h2>1. 計算の構造と目的</h2>{structure(winners)}" + (f'<div class="wrap">{part}</div>' if part else "<p>（729 の計画の結果は計算が終わりしだい載せる）</p>")
    return f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>路線の容量の最適化</title><style>{css}</style></head><body><main>{body}</main></body></html>'


def main() -> int:
    OUT.write_text(page(), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
