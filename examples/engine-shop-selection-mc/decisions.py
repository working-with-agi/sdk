#!/usr/bin/env python3
"""The map from analysis results to decisions: what is decided, from which result, on which
screen, in which section of the A4 report, by whom and when, and in which loop.

The decision report (report_a4) and the simulation screens (report.html and the other pages)
are separate things: the report says what to decide, the screens hold the material. This
table ties them together; build_a4.py prints it as appendix E and build_dashboard.py as a
panel with links.
"""

from __future__ import annotations

# (decision, analysis result / module, material to look at, screen, A4 section, who / when, loop)
DECISIONS = [
    ("年次の版（基準計画と年度予算）の承認", "baseline.py（MILP 40 本 → MC 800 本）", "年度ごとの整備費と予算、p10〜p90、欠航確率、判断期限の集中", [("budget", "年間計画と予算"), ("annual", "年間計画レポート")], "1・3", "経営・年次の版（判断ルーム）", "F"),
    ("購入計画（中寿命機の枠・プール・購入・予備）", "purchase_loop.py", "手ごとの欠航と費用の軌跡、上限（中古市場・プール）、読み返し（工場の約束・資産・契約）", [("playbook", "購入計画の輪")], "4", "経営・調達・年次。見張りが引いたら随時", "A・B"),
    ("打ち手の順番（キット → 契約 → 第二工場の選択権）", "playbook.py", "3 つの世界での費用・立て直し費・欠航の変化、ループの時間", [("playbook", "打ち手の順番")], "5", "調達・年次", "A"),
    ("国内工場の新設・段階投資", "invest.py", "3 案の NPV と実物オプション、損益分岐（補助金・第三者の入場）", [("invest", "国内工場の新設")], "1", "経営・年次", "F"),
    ("便の計画に足す便（足す計画）", "growth_plan.py・flights_plan", "需要の余地 × エンジンの余力 → 足せる便数、必要エンジン数の変化", [("demand", "客席の需要 → 足す計画")], "2", "運航・経営企画・半期", "G"),
    ("需要の前提の見直し（伸び・季節・稼働）", "plan_from_demand.py・demand.py", "直近と長期の伸びの差、引き金（3pt）、逼迫の月", [("demand", "客席の需要（一つ上の層）")], "2", "経営企画・年次。引き金で随時", "D"),
    ("退役の順序と、寿命を残す機の処分", "runout.py・typelife.py", "退役順 3 通りの入場列、残存価値、型式の晩年（部品・工期）", [("runout", "退役までの入場列")], "3", "整備計画・財務・年次", "G"),
    ("置き換え機の受領遅れへの備え（退役ペース）", "runout.py（delivery_delay）", "遅れ 6・12 か月の追加入場と費用、知っていた場合との差", [("runout", "退役までの入場列 → 受領遅れ")], "3", "運航・整備計画・月次の納期回答で", "G・B"),
    ("今月の乗り換え（今の計画を続けるか）", "track.py", "世界の事後確率、ΔV、ヒステリシス、例外の一覧", [("track", "計画の追跡"), ("tracking", "計画の追跡（別画面）"), ("monthly", "月次レポート")], "6", "整備計画・月次会議", "E・C"),
    ("不足の手当て（短期リース・代替運航）", "shortage.py", "3 か月先の欠航確率、在庫機の遅れ、短期リースの基数と費用", [("track", "計画の追跡"), ("monthly", "月次レポート")], "6", "運航・整備計画・月次。引かれたら随時", "B"),
    ("前提（世界）の追加と変化点への対応", "cpd.py", "納期回答と戻りの遅れの変化点、どの世界にも当てはまらない月", [("cpd", "変化点と前提の整合")], "6", "技術・整備計画・週次", "週次"),
    ("その場の判断（見積の承認・警報・予備の数・打診・支払い）", "usecases.py・ooda.py", "単位価値 v、承認線、暗黙のルールの案件", [("quote", "見積もりの承認"), ("trend", "状態監視の警報"), ("spares", "予備エンジンの数"), ("offer", "エンジンの打診"), ("cash", "支払いと為替")], "6", "現場・当日〜数日（会議を待たない）", "当日"),
    ("次の版で直す決め方（補正）", "backtest.py・roll.py・review.py", "被覆率、入場時期のずれ、需要の規則の採点、症状表", [("backtest", "過去で検証"), ("roll", "次の版への引き継ぎ"), ("review", "PDCA／OODA の見直し")], "7・8", "整備計画・年次", "C・G"),
    ("購入かリースか、積立金と機体価値", "tax.py・mx4.py・finance.py", "税引後 5 年の比較、積立金の推移、資産側の残価", [("tax", "税引後で比べる"), ("mx4", "積立金と機体価値"), ("finance", "お金の仕組み")], "付録 D（対話版で明細）", "財務・年次", "F"),
]

SCREENS = {  # screen key -> (file, label); report views are report.html#co=<n>&v=<key>
    "annual": ("annual.html", "年間計画レポート"), "monthly": ("monthly.html", "月次レポート"), "tracking": ("track.html", "計画の追跡（別画面）"),
}
OPTIONAL_SCREENS = [("build_whatif.py", "条件を動かして打ち手の変化を見る画面（what-if）"), ("build_room.py", "判断ルーム（承認／保留／差し戻しを共有する画面）")]


def screen_href(key: str, co: int = 0) -> str:
    return SCREENS[key][0] if key in SCREENS else f"report.html#co={co}&v={key}"


def rows_html(esc, link=None) -> str:
    """Table rows; link(key, label) renders a screen link (None -> plain text)."""
    out = []
    for d, mod, mat, screens, sec, who, loop in DECISIONS:
        sc = "、".join((link(k, l) if link else esc(l)) for k, l in screens)
        out.append(f"<tr><td><b>{esc(d)}</b></td><td>{esc(mod)}</td><td>{esc(mat)}</td><td>{sc}</td><td>{esc(sec)}</td><td>{esc(who)}</td><td>{esc(loop)}</td></tr>")
    return "".join(out)


HEAD = ["決めること", "分析（モジュール）", "判断材料", "シミュレーション画面", "A4 の章", "誰が・いつ", "輪"]
