#!/usr/bin/env python3
"""Should Japan's airlines build domestic LEAP-1B engine MRO, and how fast?

A 20-year Monte Carlo of the staged investment in data/leap_invest.json:

  stage 1  quick turns and part repairs at home (short visits no longer fly abroad)
  stage 2  performance restorations at home, with a shared engine test cell
  stage 3  third-party work for other operators (needs the OEM's licence)

What a domestic visit saves against flying the engine abroad: the round trip and the
overseas queue (fewer spare-engine months to lease), transport, and any cost gap between
the domestic and the overseas shop. Against that: capital, fixed staff and facility cost,
and the learning years. Demand follows the 737-8 deliveries (with delays) and the LEAP-1B
interval between visits; the overseas queue shrinks as world LEAP capacity catches up.

Policies compared
  outsource   keep sending everything abroad (the reference, NPV 0)
  stage1      stage 1 only
  commit12    decide stages 1 and 2 now
  commit123   decide all three now
  staged      stage 1 now; stage 2 in FY2028 only if enough aircraft have arrived and the
              overseas queue is still long; stage 3 in FY2029 only if stage 2 went ahead and
              the licence was granted

  python invest.py --json-out invest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POLICIES = {
    "outsource": "海外に出し続ける（基準）",
    "stage1": "段階 1 だけ",
    "commit12": "段階 1・2 を今決める",
    "commit123": "段階 1・2・3 を今決める",
    "staged": "段階的に決める（条件付き）",
}


def simulate(cfg: dict, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    y0, y1 = cfg["meta"]["years"]
    Y = np.arange(y0, y1 + 1)
    disc = 1 / (1 + cfg["meta"]["discount_rate"]) ** (Y - y0)
    fl, eng, ov = cfg["fleet"], cfg["engine"], cfg["overseas"]
    st = {s["id"]: s for s in cfg["stages"]}
    pts = sorted((int(k), v) for k, v in fl["aircraft_by_fy"].items())
    px, py = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    U = lambda lo_hi, size=n: rng.uniform(lo_hi[0], lo_hi[1], size)  # noqa: E731

    delay = U(fl["delay_years"])
    aircraft = np.array([np.interp(Y - d, px, py, left=0, right=py[-1]) for d in delay])  # (n, years)
    engines = aircraft * fl["engines_per_aircraft"]
    new = np.diff(np.concatenate([np.zeros((n, 1)), engines], axis=1), axis=1).clip(0)
    # shop visits: each cohort comes back every T years (T varies by engine +-20 %)
    T = U(eng["interval_cycles"]) / eng["cycles_per_year"]
    sv = np.zeros_like(engines)
    for spread in (0.8, 0.9, 1.0, 1.1, 1.2):
        Tk = T * spread
        for c in range(len(Y)):
            k = 1
            while True:
                at = c + k * Tk
                idx = np.floor(at).astype(int)
                ok = idx < len(Y)
                if not ok.any():
                    break
                sv[ok, idx[ok]] += new[ok, c] / 5
                k += 1
    qt = engines * U(eng["quick_turn_per_engine_year"])[:, None]
    price = U(eng["sv_price"])[:, None]
    q_now = U(ov["queue_months_now"])[:, None]
    q_end = U(ov["queue_normalises_by"])[:, None]
    q_long = U(ov.get("long_run_queue_months", [0, 0]))[:, None]
    queue = q_long + (q_now - q_long).clip(0) * (1 - np.clip((Y - y0) / (q_end - y0), 0, 1))
    sub = U(cfg["subsidy"]["share"]) if "subsidy" in cfg else np.zeros(n)
    subsidised = set(cfg.get("subsidy", {}).get("stages", []))
    lease, trip, tcost = ov["lease_per_month"], ov["transport_months_round_trip"], ov["transport_cost"]

    def stage_cash(s: dict, start: int, handles: str):
        """Yearly cash of one stage started in `start` (capex in the two years before)."""
        capex, fixed = U(s["capex"])[:, None], U(s["fixed_per_year"])[:, None]
        if s["id"] in subsidised:
            capex = capex * (1 - sub[:, None])
        on = (Y >= start)[None, :]
        cash = np.zeros_like(engines)
        pay = ((Y == start - 1) | (Y == start - 2))[None, :]
        cash -= pay * capex / 2
        cash -= on * fixed
        learning = ((Y >= start) & (Y < start + 2))[None, :]
        if handles == "quick_turn":
            cash += on * qt * (trip * lease + tcost + queue * lease)
        elif handles == "sv":
            gap = U(s["cost_vs_overseas"])[:, None]
            months = trip + queue - learning * 1.0   # the first two years run slower
            cash += on * sv * (months * lease + tcost + price * (1 - gap * np.where(learning, 1.1, 1.0)))
        elif handles == "third_party":
            vol = U(s["third_party_sv"])[:, None]
            ramp = np.clip((Y - start + 1) / 3, 0, 1)[None, :]
            cash += on * vol * ramp * price * U(s["margin"])[:, None]
        return cash, capex

    c1, k1 = stage_cash(st["qt"], st["qt"]["start_fy"], "quick_turn")
    c2, k2 = stage_cash(st["shop"], st["shop"]["start_fy"], "sv")
    c3, k3 = stage_cash(st["third"], st["third"]["start_fy"], "third_party")
    licence = rng.random(n) < st["third"]["license_prob"]
    c3_real = c3 * licence[:, None] + (~licence)[:, None] * np.minimum(c3, 0)  # no licence: pay, earn nothing

    trig = cfg["policy"]["staged_trigger"]
    d2 = list(Y).index(st["shop"]["decide_fy"])
    go2 = (aircraft[:, d2] >= trig["min_aircraft_at_decide"]) & (queue[:, d2] >= trig["min_queue_months"])
    go3 = go2 & licence  # by FY2029 the licence answer is known

    flows = {
        "outsource": np.zeros_like(engines),
        "stage1": c1,
        "commit12": c1 + c2,
        "commit123": c1 + c2 + c3_real,
        "staged": c1 + go2[:, None] * c2 + go3[:, None] * c3,
    }
    capex = {"outsource": 0 * k1, "stage1": k1, "commit12": k1 + k2, "commit123": k1 + k2 + k3,
             "staged": k1 + go2[:, None] * k2 + go3[:, None] * k3}
    out = {"years": Y.tolist(), "go2_share": float(go2.mean()), "go3_share": float(go3.mean()),
           "own_sv": {str(q): np.percentile(sv, q, axis=0).round(1).tolist() for q in (10, 50, 90)},
           "quick_turns": np.percentile(qt, 50, axis=0).round(1).tolist(),
           "queue_months": np.percentile(queue, 50, axis=0).round(2).tolist(),
           "aircraft": np.percentile(aircraft, 50, axis=0).round(0).tolist(), "policies": []}
    for pid, label in POLICIES.items():
        f = flows[pid]
        npv = (f * disc).sum(1)
        cum = np.cumsum(f.mean(0) * disc)
        pb = next((int(Y[i]) for i in range(len(Y)) if cum[i] > 0 and i > 0 and (cum[:i] < 0).any()), None)
        out["policies"].append({
            "id": pid, "label": label, "capex": float(capex[pid].mean()), "npv": float(npv.mean()),
            "p10": float(np.percentile(npv, 10)), "p90": float(np.percentile(npv, 90)),
            "p_positive": float((npv > 0).mean()) if pid != "outsource" else None,
            "payback": pb, "cum_mean": cum.round(1).tolist(),
        })
    return out


def breakeven(cfg: dict, draws: int, seed: int) -> dict:
    """Mean NPV of 'all three stages now' over a grid of subsidy share x third-party
    volume: where the investment starts to pay."""
    subs, vols = [0.0, 0.25, 0.5, 0.75], [0, 40, 80, 120, 160]
    grid = []
    for s_ in subs:
        row = []
        for v in vols:
            c = json.loads(json.dumps(cfg))
            c["subsidy"]["share"] = [s_, s_]
            for st in c["stages"]:
                if st["id"] == "third":
                    st["third_party_sv"] = [v, v]
                    st["license_prob"] = 1.0 if v else 0.0
            r = simulate(c, draws, seed)
            row.append(round(next(p["npv"] for p in r["policies"] if p["id"] == "commit123"), 1))
        grid.append(row)
    return {"subsidy": subs, "third_party_sv": vols, "npv": grid,
            "note": "段階 1・2・3 を今決めた場合の正味現在価値（百万ドル）。受託件数はメーカーの認可が得られた前提"}


def summarise(res: dict) -> dict:
    P = {p["id"]: p for p in res["policies"]}
    cand = [p for p in res["policies"] if p["id"] != "outsource"]
    best = max(cand, key=lambda p: p["npv"])
    staged, c12 = P["staged"], P["commit12"]
    headline = (f"{best['label']}のが最も得（正味現在価値 {best['npv']:+.0f} 百万ドル、得になる確率 {best['p_positive']:.0%}）"
                if best["npv"] > 0 else "どの案も、海外に出し続けるより得にならない見込み")
    why = (f"段階 2 を今決めると {c12['npv']:+.0f} 百万ドル（10〜90% で {c12['p10']:+.0f}〜{c12['p90']:+.0f}）。"
           f"条件付きにすると、進む筋書きは {res['go2_share']:.0%}、受託まで進むのは {res['go3_share']:.0%}。"
           f"自社の入場は定常で年 {res['own_sv']['50'][-1]:.0f} 件前後と、海外の標準的な工場（年 300〜350 件）より一桁小さい。")
    return {"headline": headline, "why": why, "best": {"id": best["id"], "npv": best["npv"] * 1000},
            "recommend": {"go": best["npv"] > 0, "policy": best["label"]}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "data" / "leap_invest.json")
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json-out", type=Path, default=Path("invest.json"))
    args = ap.parse_args(argv)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    res = simulate(cfg, args.draws, args.seed)
    res |= summarise(res)
    res["breakeven"] = be = breakeven(cfg, max(500, args.draws // 4), args.seed)
    # third-party volume at which all three stages pay, without subsidy (linear between grid points)
    row, vols = be["npv"][0], be["third_party_sv"]
    cross = next((vols[i] + (vols[i + 1] - vols[i]) * -row[i] / (row[i + 1] - row[i])
                  for i in range(len(row) - 1) if row[i] < 0 <= row[i + 1]), None)
    be["breakeven_sv_no_subsidy"] = cross
    if not res["recommend"]["go"] and cross is not None:
        per25 = (be["npv"][1][0] - be["npv"][0][0])
        res["headline"] = (f"自社の入場だけでは得にならない。受託が年 {cross:.0f} 件を超えれば得になる"
                           f"（補助 25% ごとの効きは約 {per25:.0f} 百万ドルと小さい）")
    res["note"] = ("数字の多くは推定（確度 C）。とくに国内の整備費が海外より高いか安いか、メーカーの認可条件、"
                   "受託の件数、試運転設備の分担は非公開。正味現在価値は 2026 年度を基準に割引率 7%。")
    res["sources"] = {s["id"]: s["source"] for s in cfg["stages"]} | {
        "fleet": cfg["fleet"]["source"], "interval": cfg["engine"]["interval_source"], "queue": cfg["overseas"]["queue_source"]}
    args.json_out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in res["policies"]:
        print(f"{p['label']:<22} capex {p['capex']:6.0f}  NPV {p['npv']:+7.0f} (p10 {p['p10']:+6.0f}, p90 {p['p90']:+6.0f})"
              + (f"  P>0 {p['p_positive']:.0%}" if p["p_positive"] is not None else "") + f"  payback {p['payback']}")
    print(res["headline"]); print(res["why"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
