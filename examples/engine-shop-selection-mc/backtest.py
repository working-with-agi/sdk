#!/usr/bin/env python3
"""Use the past as the test: the same planning method run at many earlier dates,
checked against what then happened (過去のシミュレーションを検証に当てる).

Two backtests:
  engine plan   the 20-year simulation is the company's history. At each of the last N
                October versions the 2-year plan is rebuilt from the history cut there
                (history.build) and compared with the visits the history then produced:
                timing error of the forecast limits, volume and spend per fiscal year,
                whether the actual count fell in the 10-90 % range (calibration: should be
                ~80 %), unscheduled removals assumed vs seen, and how much of one
                version survived into the next. The verdict says what the method gets
                right and what to widen or shift.
  demand growth the real market series (e-Stat fiscal years 2018-2025): at each year the
                growth rule (recent 2-year trend, long-run trend, and the plan's blend)
                is applied with only the data then available and compared with what the
                next year actually did; the early-review trigger is checked too.

  python backtest.py jal --out backtest/jal.json

Learn / check / use: the versions at years 6-14 of the history are the learning period
(the corrections -- timing shift, unscheduled ratio, share of planned visits kept -- are
derived there), the versions at years 15-19 are the checking period (the raw and the
corrected method are scored there, out of sample), and from today on the corrected
method is used only if it scored better.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import demand
import history
import plan_from_demand as pfd

HERE = Path(__file__).resolve().parent


LEARN_BACKS = tuple(range(14, 5, -1))     # versions at years 6..14 of the 20-year history: learn the corrections here
TEST_BACKS = tuple(range(5, 0, -1))       # versions at years 15..19: score the corrected method out of sample
DRAWS = 4000


def _metrics(vs: list[dict], corr: dict | None, rng) -> dict:
    """Score a set of versions, optionally with the learned corrections applied to the
    forecasts (timing shift), the unscheduled rate (ratio) and the share of planned visits
    that happen in their fiscal year (p_keep)."""
    shift = corr["timing_shift"] if corr else 0
    u = corr["unsched_ratio"] if corr else 1.0
    pk = corr["p_keep"] if corr else 0.85
    errs, inside, n_fy, planned, actual, uns_e, uns_a, pred = [], 0, 0, 0, 0, 0.0, 0, 0.0
    for v in vs:
        errs += [t["actual"] - (t["forecast"] + shift) for t in v["timing"] if t["actual"] is not None]
        for f in v["fiscal_years"]:
            if f["months"] < 6:
                continue
            n_fy += 1
            lam = f["unsched_expected"] * u
            sims = rng.binomial(f["planned"], pk, DRAWS) + rng.poisson(lam, DRAWS)
            lo, hi = np.percentile(sims, 10), np.percentile(sims, 90)
            inside += int(lo <= f["actual"] <= hi)
            planned += f["planned"]; actual += f["actual"]; uns_e += lam; uns_a += f["unsched_actual"]
            pred += f["planned"] * pk + lam
    n = len(errs)
    return {"versions": len(vs), "n_fy": n_fy, "coverage": inside / max(1, n_fy), "timing_mean": float(np.mean(errs)) if errs else None,
            "timing_within_1": (sum(1 for e in errs if abs(e) <= 1) / n) if n else None, "n_timing": n,
            "volume_ratio": actual / max(1, planned), "predicted_ratio": actual / max(1e-9, pred), "unsched_ratio": uns_a / max(1e-9, uns_e)}


def learn_corrections(vs: list[dict]) -> dict:
    errs = [t["actual"] - t["forecast"] for v in vs for t in v["timing"] if t["actual"] is not None]
    fys = [f for v in vs for f in v["fiscal_years"] if f["months"] >= 6]
    uns_ratio = sum(f["unsched_actual"] for f in fys) / max(1e-9, sum(f["unsched_expected"] for f in fys))
    p_keep = sum(f["actual"] - f["unsched_actual"] for f in fys) / max(1, sum(f["planned"] for f in fys))
    return {"timing_shift": int(round(float(np.mean(errs)))) if errs else 0, "unsched_ratio": round(uns_ratio, 3), "p_keep": round(min(1.0, max(0.3, p_keep)), 3),
            "how": {"timing_shift": "学ぶ期間の予測誤差（実際 − 予測）の平均を、期限の予測に足す（か月、整数）",
                    "unsched_ratio": "学ぶ期間の計画外取卸し 実績 ÷ 想定 を、想定率に掛ける",
                    "p_keep": "学ぶ期間で、計画した入場がその年度に実際に起きた割合（幅の計算の二項確率。既定 0.85）"}}


def split_backtest(h: dict, rng) -> dict:
    """Learn on the early versions, score raw and corrected on the late ones."""
    by = {v["back"]: v for v in h["versions"] if v["realised_months"] >= 12}
    learn = [by[b] for b in LEARN_BACKS if b in by]
    test = [by[b] for b in TEST_BACKS if b in by]
    corr = learn_corrections(learn)
    out = {"learn_backs": [v["back"] for v in learn], "test_backs": [v["back"] for v in test], "learn_versions": [v["version"] for v in learn], "test_versions": [v["version"] for v in test],
           "corrections": corr, "learn": _metrics(learn, None, rng), "test_raw": _metrics(test, None, rng), "test_corrected": _metrics(test, corr, rng)}
    a, b = out["test_raw"], out["test_corrected"]
    better = []
    if a["timing_mean"] is not None:
        better.append(("timing", abs(b["timing_mean"]) < abs(a["timing_mean"]), f"期限の誤差 平均 {a['timing_mean']:+.1f} → {b['timing_mean']:+.1f} か月、±1 か月以内 {a['timing_within_1']:.0%} → {b['timing_within_1']:.0%}"))
    better.append(("coverage", abs(b["coverage"] - 0.8) < abs(a["coverage"] - 0.8), f"幅に入った年度 {a['coverage']:.0%} → {b['coverage']:.0%}（目標 80%）"))
    better.append(("volume", abs(b["predicted_ratio"] - 1) < abs(a["predicted_ratio"] - 1), f"年度の件数 実績 ÷ 予測 {a['predicted_ratio']:.2f} → {b['predicted_ratio']:.2f}"))
    n_better = sum(1 for _, ok, _ in better if ok)
    out["verdict"] = [{"status": "ok" if ok else "warn", "text": t} for _, ok, t in better]
    out["summary"] = {"better": n_better, "of": len(better),
                      "text": (f"学ぶ期間（{out['learn_versions'][0]}〜{out['learn_versions'][-1]} 版）で導いた補正を、確かめる期間（{out['test_versions'][0]}〜{out['test_versions'][-1]} 版）に当てると "
                               f"{len(better)} 指標中 {n_better} が改善" + ("：補正は使う期間に持ち込める" if n_better == len(better) else "：改善しない指標の補正は過学習の疑い、使う期間には持ち込まない")) if learn and test else "版が足りない"}
    return out


def engine_backtest(cid: str, years: int, scenarios: int = 30) -> dict:
    years = max(years, max(LEARN_BACKS))
    history.VERSIONS = tuple(range(years, -1, -1))
    h = history.build(cid, scenarios=scenarios)
    split = split_backtest(h, np.random.default_rng(7))
    vs = [v for v in h["versions"] if v["realised_months"] >= 12]
    errs, matched, early, late, within1, unsched = [], 0, 0, 0, 0, 0
    per = []
    fy_rows = []
    for v in vs:
        e = [t["actual"] - t["forecast"] for t in v["timing"] if t["actual"] is not None]
        n_unsched = sum(1 for t in v["timing"] if t["actual"] is not None and t["unscheduled"])
        missed = sum(1 for t in v["timing"] if t["actual"] is None)          # forecast due, not removed in the realised months
        errs += e; matched += len(e); unsched += n_unsched
        early += sum(1 for x in e if x < -1); late += sum(1 for x in e if x > 1); within1 += sum(1 for x in e if abs(x) <= 1)
        fys = [f for f in v["fiscal_years"] if f["months"] >= 6]
        fy_rows += [{**f, "version": v["version"]} for f in fys]
        per.append({"version": v["version"], "planned": v["planned"], "matched": len(e), "missed": missed, "unplanned": v["unplanned"],
                    "timing_mean": float(np.mean(e)) if e else None, "timing_sd": float(np.std(e)) if e else None,
                    "fy": [{k: f[k] for k in ("fy", "months", "planned", "actual", "p10", "p90", "inside", "planned_spend", "actual_spend", "unsched_expected", "unsched_actual")} for f in fys]})
    n_fy = len(fy_rows)
    coverage = sum(1 for f in fy_rows if f["inside"]) / max(1, n_fy)
    vol_ratio = sum(f["actual"] for f in fy_rows) / max(1, sum(f["planned"] for f in fy_rows))
    spend_ratio = sum(f["actual_spend"] for f in fy_rows) / max(1, sum(f["planned_spend"] for f in fy_rows))
    uns_ratio = sum(f["unsched_actual"] for f in fy_rows) / max(1e-9, sum(f["unsched_expected"] for f in fy_rows))
    hist = np.histogram(errs, bins=list(range(-12, 13)))[0].tolist() if errs else []
    verdict = []
    if n_fy:
        verdict.append(("ok" if 0.7 <= coverage <= 0.9 else "warn", f"リスクの幅（10〜90%）に実績が入った年度 {coverage:.0%}（{sum(1 for f in fy_rows if f['inside'])}/{n_fy}、目標 80%）"
                        + ("" if 0.7 <= coverage <= 0.9 else "：幅が狭い（前提の分散を広げる）" if coverage < 0.7 else "：幅が広すぎる（分散を絞れる）")))
    if errs:
        m = float(np.mean(errs))
        verdict.append(("ok" if abs(m) <= 1 else "warn", f"期限の予測誤差 平均 {m:+.1f} か月、±1 か月以内 {within1 / matched:.0%}、早すぎ {early / matched:.0%}・遅すぎ {late / matched:.0%}（n={matched}）"
                        + ("" if abs(m) <= 1 else "：期限が実際より早い（保守的）。窓の下端を後ろへ" if m > 1 else "：期限が実際より遅い。劣化率の前提を上げる")))
    verdict.append(("ok" if 0.85 <= vol_ratio <= 1.15 else "warn", f"入場の件数 実績 ÷ 計画 {vol_ratio:.2f}、費用 {spend_ratio:.2f}"))
    verdict.append(("ok" if 0.7 <= uns_ratio <= 1.4 else "warn", f"計画外取卸し 実績 ÷ 想定 {uns_ratio:.2f}"))
    if h["stability"]:
        ks = float(np.mean([s["kept_share"] for s in h["stability"]]))
        verdict.append(("ok" if ks >= 0.5 else "info", f"前の版の 2 年目が次の版の 1 年目にそのまま残った割合 平均 {ks:.0%}（版の安定性）"))
    return {"versions": per, "n_versions": len(vs), "n_fy": n_fy, "coverage": coverage, "volume_ratio": vol_ratio, "spend_ratio": spend_ratio,
            "unsched_ratio": uns_ratio, "timing": {"n": matched, "mean": float(np.mean(errs)) if errs else None, "sd": float(np.std(errs)) if errs else None,
                                                   "within_1": within1 / max(1, matched), "early": early / max(1, matched), "late": late / max(1, matched),
                                                   "unscheduled_share": unsched / max(1, matched), "hist_bins": list(range(-12, 13)), "hist": hist},
            "stability": h["stability"], "verdict": [{"status": s, "text": t} for s, t in verdict], "split": split,
            "note": "真実は同じ 20 年シミュレーションの続き（合成）。各版はその時点までの履歴だけから同じ方法で作り、その後の 12〜24 か月と突き合わせる"}


def demand_backtest(D: dict) -> dict:
    fy = D["market"]["fiscal_years"]
    rpk = {int(f["fy"][2:]): f["rpk"] for f in fy}
    ys = sorted(rpk)
    rows = []
    for y in ys:
        if y - 3 not in rpk:
            continue
        short = (rpk[y - 1] / rpk[y - 3]) ** 0.5 - 1
        y0 = ys[0]
        long = ((rpk[y - 1] / rpk[y0]) ** (1 / (y - 1 - y0)) - 1) if y - 1 > y0 else short
        blend = pfd.growth_at(12, short, long)
        real = rpk[y] / rpk[y - 1] - 1
        rows.append({"fy": f"FY{y}", "short": round(short, 4), "long": round(long, 4), "blend": round(blend, 4), "realised": round(real, 4),
                     "err_short": round(real - short, 4), "err_long": round(real - long, 4), "err_blend": round(real - blend, 4),
                     "trigger_fired": bool(abs(real - short) > pfd.TRIGGER_PT), "shock": bool(abs(real) > 0.15)})
    normal = [r for r in rows if not r["shock"]]
    mae = lambda k, rs: float(np.mean([abs(r[k]) for r in rs])) if rs else None  # noqa: E731
    verdict = []
    if rows:
        verdict.append(("info", f"検証した年度 {len(rows)}、うち衝撃の年（前年比 ±15% 超）{sum(1 for r in rows if r['shock'])}：どの規則も外す。引き金（3pt）は {sum(1 for r in rows if r['trigger_fired'])} 年度で引かれた"))
    if normal:
        best = min(("short", "long", "blend"), key=lambda k: mae(f"err_{k}", normal))
        verdict.append(("ok" if best != "short" else "warn", f"平常の年の平均誤差：直近 {mae('err_short', normal):.1%}、長期 {mae('err_long', normal):.1%}、計画の混ぜ方 {mae('err_blend', normal):.1%} → {dict(short='直近', long='長期', blend='混ぜ方')[best]}が最も近い"))
    return {"rows": rows, "mae": {"short": mae("err_short", rows), "long": mae("err_long", rows), "blend": mae("err_blend", rows),
                                  "short_normal": mae("err_short", normal), "long_normal": mae("err_long", normal), "blend_normal": mae("err_blend", normal)},
            "verdict": [{"status": s, "text": t} for s, t in verdict],
            "note": "実データ（e-Stat 年度系列）。各年度は前年度までのデータだけで規則を当て、その年度の実績と比べる。直近＝前 2 年の年率、長期＝FY2018 からの年率、混ぜ方＝計画が 12 か月先に使う値"}


def build(cid: str, years: int, scenarios: int) -> dict:
    return {"company": cid, "engine": engine_backtest(cid, years, scenarios), "demand": demand_backtest(demand.load()),
            "note": "過去を検証に当てる：同じ方法を過去の各時点で回し、その後に起きたことと比べる"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--years", type=int, default=14, help="how many past October versions (at least the learn period)")
    ap.add_argument("--scenarios", type=int, default=30)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = build(a.company, a.years, a.scenarios)
    p = a.out or HERE / "backtest" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    e = out["engine"]
    print(f"{a.company}: {e['n_versions']} versions, {e['n_fy']} fiscal years; coverage {e['coverage']:.0%}, volume x{e['volume_ratio']:.2f}, spend x{e['spend_ratio']:.2f}, "
          f"unsched x{e['unsched_ratio']:.2f}, timing mean {e['timing']['mean']:+.1f} sd {e['timing']['sd']:.1f} (n={e['timing']['n']}, within ±1: {e['timing']['within_1']:.0%})")
    for v in e["verdict"] + out["demand"]["verdict"]:
        print(f"  [{v['status']}] {v['text']}")
    sp = e["split"]
    print(f"  split: corrections {sp['corrections']['timing_shift']:+d} mo, unsched x{sp['corrections']['unsched_ratio']}, p_keep {sp['corrections']['p_keep']} | {sp['summary']['text']}")
    for v in sp["verdict"]:
        print(f"    [{v['status']}] {v['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
