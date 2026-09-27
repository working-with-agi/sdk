#!/usr/bin/env python3
"""The engine plan to the end of the fleet: every engine's chain of shop visits from today
to the day it leaves (退役までの入場列).

The 2-year plan answers "which engine, when, which workscope" inside a window. The window
is one piece of a longer question the fleet planner actually holds: how many more times
does each engine go to the shop before the type is retired, what does each of those visits
have to restore so the engine *just* reaches its exit, and which engines should leave first
so the fewest expensive visits are bought for life that is then thrown away.

Model (deterministic mean physics, the same constants as lifecycle.py)
  state         EGT margin, LLP cycles left (core / LP / fan), cycles since the last visit
  flying        mean cycles per month of the company's sub-fleets; margin falls by the
                initial drop over the first 1,000 cycles, then at the mature rate
  removal       margin < 3 degC or a stack < 1,500 cycles
  workscope     inside the frozen window: the plan's own visit (authoritative);
                after it: the lightest workscope that carries the engine to its exit
                (run-out); if none does, the usual stub rule (lifecycle.workscope)
  exit          the transition retires one aircraft every `every_months` from `start`
                (companies.json); each retirement releases two engine positions. Which
                engines leave is a policy:
                  next_due   the serviceable engine closest to its next removal leaves
                             first (avoids the most visits; the usual practice)
                  oldest     the engine with the fewest LLP cycles left leaves first
                  random     any (a reference)
  residual      what leaves with the engine: LLP cycles and run months not used, priced
                with the half-life convention (data/mx4_params.json); a green-time engine
                is one that leaves with more than a typical run's worth of life

  python runout.py jal --out runout/jal.json

Everything is synthetic; the retirement cadence carries no_source in companies.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import lifecycle
import mx4

HERE = Path(__file__).resolve().parent
MAX_MONTHS = 15 * 12
EXIT_RATE = 4          # engines that can leave (sale, part-out, lease-out) in one month after the window (assumption)
POLICIES = ("next_due", "oldest", "random")


def month_label(start: str, t: int) -> str:
    y, m = (int(x) for x in start.split("-"))
    m0 = y * 12 + (m - 1) + t
    return f"{m0 // 12}-{m0 % 12 + 1:02d}"


def load_inputs(cid: str, baseline_path: Path | None = None):
    conf = json.loads((HERE / "data" / "companies.json").read_text(encoding="utf-8"))
    cfg = conf["companies"][cid]
    b = json.loads((baseline_path or HERE / "baselines" / f"{cid}-2026-10.json").read_text(encoding="utf-8"))
    fleet = json.loads((HERE / b["paths"]["fleet"]).read_text(encoding="utf-8"))
    shops = json.loads((HERE / b["paths"]["shops"]).read_text(encoding="utf-8"))
    return cfg, b, fleet, shops


class Physics:
    """Mean deterioration for one company (companies.json wear / sub-fleets / LLP lives)."""

    def __init__(self, cfg: dict, fleet: dict):
        w = cfg.get("wear", {})
        subs = cfg.get("subfleets") or fleet.get("meta", {}).get("derivation", {}).get("subfleets") or []
        tot = sum(x["aircraft"] for x in subs) or 1
        self.cpm = (sum(x["aircraft"] * x["cycles_per_year"] for x in subs) / tot / 12) if subs else lifecycle.CYCLES_PER_MONTH
        sev = (sum(x["aircraft"] * lifecycle.leg_factor(x["fh_per_cycle"]) * x.get("climate", 1.0) for x in subs) / tot) if subs else 1.0
        self.initial_drop = float(w.get("initial_drop", lifecycle.INITIAL_DROP))
        self.loss_per_cycle = float(w.get("mature_loss_per_1000", lifecycle.EGT_LOSS_PER_1000)) / 1000 * sev
        self.restore = {k: float(v) for k, v in w.get("restore", lifecycle.RESTORE).items()}
        lives = cfg.get("llp_lives", {})
        self.life = {"core": lives.get("core", lifecycle.CORE_LIFE), "lp": lives.get("lp", lifecycle.LP_LIFE), "fan": w.get("fan_life") or 10 ** 9}
        self.min_margin, self.min_llp = lifecycle.MIN_MARGIN, lifecycle.MIN_LLP
        self.run_cycles = (self.restore["PR"] - self.initial_drop - self.min_margin) / self.loss_per_cycle

    def months_of_margin(self, margin: float, since: float, wear: float = 1.0) -> float:
        """Months of flying until the EGT limit from this state (wear = engine-specific
        multiplier on the mature loss rate, 1 = fleet median)."""
        early = max(0.0, 1000 - since)
        c = 0.0
        m = margin
        if early > 0:
            drop_early = self.initial_drop * early / 1000
            if m - drop_early <= self.min_margin:
                return (m - self.min_margin) / (self.initial_drop / 1000) / self.cpm
            m -= drop_early
            c += early
        c += max(0.0, m - self.min_margin) / (self.loss_per_cycle * wear)
        return c / self.cpm

    def months_to_removal(self, s: dict) -> float:
        llp = min(s["core"], s["lp"], s["fan"]) - self.min_llp
        return max(0.0, min(self.months_of_margin(s["margin"], s["since"], s.get("wear", 1.0)), llp / self.cpm))

    def fly(self, s: dict, months: float = 1.0) -> None:
        cyc = self.cpm * months
        early = max(0.0, min(cyc, 1000 - s["since"]))
        s["margin"] -= self.initial_drop * early / 1000 + self.loss_per_cycle * s.get("wear", 1.0) * (cyc - early)
        s["since"] += cyc
        for k in ("core", "lp", "fan"):
            s[k] -= cyc

    def restore_state(self, s: dict, ws: str) -> None:
        s["margin"] = self.restore[ws]
        s["since"] = 0.0
        if ws in ("CORE", "FULL"):
            s["core"] = self.life["core"]
        if ws == "FULL":
            s["lp"] = self.life["lp"]
            if s["fan"] < self.min_llp + lifecycle.STUB_TOLERANCE * self.run_cycles:
                s["fan"] = self.life["fan"]

    def runout_workscope(self, s: dict, months_needed: float, allowed: list[str]) -> tuple[str, float]:
        """The lightest allowed workscope that carries the engine `months_needed` months;
        else the stub rule. Returns (workscope, months it lasts)."""
        best = None
        for ws in ("PR", "CORE", "FULL"):
            if ws not in allowed:
                continue
            trial = dict(s)
            self.restore_state(trial, ws)
            lasts = self.months_to_removal(trial)
            best = (ws, lasts)
            if lasts >= months_needed:
                return ws, lasts
        stub = lifecycle.workscope(s["core"], s["lp"], self.run_cycles, s["fan"])
        if stub in allowed:
            trial = dict(s); self.restore_state(trial, stub)
            return stub, self.months_to_removal(trial)
        return best if best else ("FULL", 0.0)


def retirement_schedule(cfg: dict, fleet: dict, start: str) -> list[int]:
    """Month index of each aircraft's exit (two engine positions each)."""
    tr = fleet.get("transition") or cfg.get("transition") or {}
    n_ac = cfg["aircraft"]["total"]
    if not tr.get("start"):
        return []
    y, m = (int(x) for x in tr["start"].split("-"))
    y0, m0 = (int(x) for x in start.split("-"))
    t0 = (y * 12 + m - 1) - (y0 * 12 + m0 - 1)
    every = int(tr.get("every_months", 2))
    return [t0 + i * every for i in range(n_ac)]


DELIVERY_DELAYS = (6, 12)   # months the new type's deliveries slip in the scenarios (assumption)


def simulate(cfg: dict, b: dict, fleet: dict, shops: dict, policy: str = "next_due", seed: int = 11, exit_hint: dict | None = None,
             delivery_delay: int = 0) -> dict:
    ph = Physics(cfg, fleet)
    P = mx4.load_params()
    price = {ws: q["price"] for ws, q in shops["shops"][0]["quotes"].items()}
    tat = {ws: q["tat"] + shops["shops"][0].get("transport_months", 0) for ws, q in shops["shops"][0]["quotes"].items()}
    start, W = fleet["start"], fleet["horizon_months"]
    plan = {r["esn"]: r for r in b["plan"]}
    rng = np.random.default_rng(seed)
    exits = [x + delivery_delay for x in retirement_schedule(cfg, fleet, start)]
    end = (max(exits) + 1) if exits else MAX_MONTHS
    end = min(end, MAX_MONTHS)
    # engines: the fleet's due list carries the state; the rest of the owned engines are
    # "not due in the window" and get a synthetic state spread over a run
    eng = {}
    snap = {x["esn"]: x for x in (fleet.get("engine_state") or {}).get("engines", [])}
    for e in fleet["engines"]:
        st = snap.get(e["esn"], {})
        eng[e["esn"]] = {"esn": e["esn"], "margin": float(e["egt_margin"]), "since": float(st.get("cycles_since_visit", 1500.0)),
                         "core": float(e["llp_remaining"]["core"]), "lp": float(e["llp_remaining"]["lp"]), "fan": float(e["llp_remaining"].get("fan", ph.life["fan"])),
                         "allowed": e["allowed_workscopes"], "back": 0, "chain": [], "retired": None, "from_plan": True, "wear": float(st.get("wear_factor", 1.0))}
    # the engines not due inside the window: their state comes from the same 20-year
    # simulation (fleet.engine_state); only when a fleet file predates it is a spread assumed
    n_extra = max(0, fleet["owned_engines"] - len(eng))
    extras = [x for esn, x in snap.items() if esn not in eng][:n_extra]
    state_source = "simulation" if extras else "assumed"
    for x in extras:
        eng[x["esn"]] = {"esn": x["esn"], "margin": float(x["egt_margin"]), "since": float(x["cycles_since_visit"]),
                         "core": float(x["llp_remaining"]["core"]), "lp": float(x["llp_remaining"]["lp"]), "fan": float(x["llp_remaining"].get("fan", ph.life["fan"])),
                         "allowed": ["PR", "CORE", "FULL"], "back": int(x.get("back_in_months", 0)), "chain": [], "retired": None, "from_plan": False, "wear": float(x.get("wear_factor", 1.0))}
    for i in range(n_extra - len(extras)):
        esn = f"{fleet['engines'][0]['esn'].split('-')[0]}-X{i + 1:03d}"
        frac = rng.uniform(0.05, 0.6)     # part of a run already flown; not due inside the window by construction
        cyc = frac * ph.run_cycles
        eng[esn] = {"esn": esn, "margin": ph.restore["PR"] - ph.initial_drop - ph.loss_per_cycle * max(0.0, cyc - 1000), "since": cyc,
                    "core": rng.uniform(ph.life["core"] * 0.35, ph.life["core"]), "lp": rng.uniform(ph.life["lp"] * 0.35, ph.life["lp"]),
                    "fan": rng.uniform(ph.life["fan"] * 0.35, ph.life["fan"]) if ph.life["fan"] < 10 ** 8 else ph.life["fan"],
                    "allowed": ["PR", "CORE", "FULL"], "back": 0, "chain": [], "retired": None, "from_plan": False}
    n_ac = cfg["aircraft"]["total"]
    req_w = fleet.get("required_positions") or []
    buf_w = fleet.get("buffer_spares") or []
    spare_ratio = max(0.0, fleet["owned_engines"] - 2 * n_ac) / (2 * n_ac)   # spares per installed engine, kept constant as the fleet shrinks
    buffer_min = int(fleet["buffer_spares"][-1]) if fleet.get("buffer_spares") else 2
    exit_ptr = 0
    retire_order = []
    visits = []

    def aircraft_left(t: int) -> int:
        # inside the window the frozen plan's schedule holds (its required-positions series
        # keeps the fleet flying; part-outs are its own decision), so exits count from the
        # end of the window
        return n_ac if t < W else n_ac - sum(1 for x in exits if x <= t)

    def positions_needed(t: int) -> int:
        if t < W and t < len(req_w):
            return int(req_w[t]) + (int(buf_w[t]) if t < len(buf_w) else buffer_min)
        left = aircraft_left(t)
        return 2 * left + max(buffer_min, int(np.ceil(2 * left * spare_ratio)))

    # the operations side, month by month: what the schedule needs to fly (flight index,
    # airframe checks, the aircraft still in service) against what the engine plan leaves
    # serviceable; inside the window the plan's own required/buffer series is used
    idx = fleet.get("meta", {}).get("derivation", {}).get("flight_index") or lifecycle.FLIGHT_INDEX
    checks = fleet.get("meta", {}).get("derivation", {}).get("airframe_checks") or lifecycle.AIRFRAME_CHECKS
    base_needed = fleet.get("meta", {}).get("derivation", {}).get("base_aircraft_needed") or cfg["aircraft"].get("base_needed", n_ac)
    y0, m0 = (int(x) for x in start.split("-"))

    def required_flying(t: int) -> int:
        if t < len(req_w):
            return int(req_w[t])
        m = (m0 - 1 + t) % 12 + 1
        left = aircraft_left(t)
        need = min(left - int(checks.get(str(m), checks.get(m, 0)) * left / n_ac), int(np.ceil(base_needed * left / n_ac * float(idx.get(str(m), idx.get(m, 1.0))))))
        return 2 * max(0, need)

    ops = []

    for t in range(end):
        # retirements this month: release positions, retire engines by policy
        while exit_ptr < len(exits) and exits[exit_ptr] <= t:
            exit_ptr += 1
        alive = [s for s in eng.values() if s["retired"] is None]
        # inside the window nothing leaves (the surplus is the plan's own spare inventory);
        # after it, engines leave as the transition frees positions, at most EXIT_RATE a month
        surplus = min(EXIT_RATE, len(alive) - positions_needed(t)) if t >= W else 0
        if surplus > 0:
            # a serviceable engine; inside the window an engine with a planned visit still to
            # come is committed (slot booked, kit ordered) and does not leave before it
            cand = [s for s in alive if s["back"] <= t and not (s["esn"] in plan and plan[s["esn"]]["t"] >= t and t < W)] or alive
            if policy == "next_due":
                cand.sort(key=lambda s: ph.months_to_removal(s))
            elif policy == "oldest":
                cand.sort(key=lambda s: min(s["core"], s["lp"], s["fan"]))
            else:
                rng.shuffle(cand)
            for s in cand[:surplus]:
                s["retired"] = t
                s["due_in_at_exit"] = round(ph.months_to_removal(s), 1)
                retire_order.append(s["esn"])
        alive = [s for s in eng.values() if s["retired"] is None]
        in_shop = sum(1 for s in alive if s["back"] > t)
        req = required_flying(t)
        buf = int(buf_w[t]) if t < len(buf_w) else max(buffer_min, int(np.ceil(2 * aircraft_left(t) * spare_ratio)))
        ops.append({"t": t, "label": month_label(start, t), "aircraft": aircraft_left(t), "required": req, "buffer": buf,
                    "owned": len(alive), "in_shop": in_shop, "serviceable": len(alive) - in_shop, "margin": len(alive) - in_shop - req - buf})
        # fly the serviceable ones, remove the due ones
        for s in eng.values():
            if s["retired"] is not None or s["back"] > t:
                continue
            r = plan.get(s["esn"])
            planned = r is not None and r["t"] == t and not any(c["t"] == t for c in s["chain"])
            due = s["margin"] < ph.min_margin or min(s["core"], s["lp"], s["fan"]) < ph.min_llp
            if planned or (due and t >= W):
                if planned:
                    ws, reason = r["workscope"], "計画"
                    trial = dict(s); ph.restore_state(trial, ws); lasts = ph.months_to_removal(trial)
                else:
                    hint = (exit_hint or {}).get(s["esn"])
                    need = (hint - t) if hint is not None else (end - t)
                    ws, lasts = ph.runout_workscope(s, need, s["allowed"] if s["from_plan"] else ["PR", "CORE", "FULL"])
                    reason = "EGT" if s["margin"] < ph.min_margin else "LLP"
                    if hint is not None and lasts >= need:
                        reason += "・退役まで持つ最軽の範囲"
                # what the visit throws away is nothing (engine is at its limit); record the state before
                v = {"t": t, "label": month_label(start, t), "ws": ws, "cost_k": price[ws], "reason": reason, "off_wing": tat[ws],
                     "margin_before": round(s["margin"], 1), "llp_before": int(min(s["core"], s["lp"], s["fan"])), "lasts_months": round(lasts, 1)}
                ph.restore_state(s, ws)
                s["back"] = t + tat[ws]
                s["chain"].append(v)
                visits.append({"esn": s["esn"], **v})
                continue
            if due and t < W:
                # inside the window the plan is authoritative; an engine at its limit without a
                # planned visit is a plan gap (flag, keep flying on paper)
                if not any(c.get("gap") for c in s["chain"]):
                    slack = (r["t"] - t) if r else None
                    s["chain"].append({"t": t, "label": month_label(start, t), "ws": None, "cost_k": 0, "gap": True, "slack_months": slack,
                                       "reason": f"平均の劣化では {slack} か月早く限界（計画の入場 {r['month']}）" if r else "窓の中で限界だが計画に入場なし"})
            ph.fly(s)
    # residual at exit
    rows = []
    for s in eng.values():
        rt = s["retired"]
        llp_left = min(s["core"], s["lp"], s["fan"])
        run_left = ph.months_to_removal(s)
        resid_k = max(0.0, llp_left - ph.min_llp) * P["llp_value_per_cycle_k"] + run_left * P["pr_value_per_month_k"]
        chain = [c for c in s["chain"] if not c.get("gap")]
        last = chain[-1] if chain else None
        due_in = s.get("due_in_at_exit")
        if rt is None:
            note = "最終退役より後まで残る（窓の後の状態は仮定）"
        elif not s["from_plan"] and not chain:
            src = "状態はシミュレーションの続き" if state_source == "simulation" else "状態は非公表・仮定"
            note = (f"窓の外の機（{src}）。限界の {due_in} か月前に退役し、入場を 1 回避けた" if due_in is not None and due_in < 12
                    else f"窓の外の機（{src}）。入場なしで退役、翼上 {run_left:.0f} か月を残す")
        elif last and last["reason"].startswith("計画") and rt - last["t"] < 30:
            note = f"計画の入場（{last['label']} {last['ws']}）のあと退役まで {rt - last['t']} か月。買った寿命の一部を捨てる"
        elif last and "最軽" in last["reason"]:
            note = f"{last['label']} は退役まで持つ最軽の範囲 {last['ws']}（{last['lasts_months']} か月持つ、退役まで {rt - last['t']}）"
        elif last:
            note = f"{last['label']} {last['ws']}（{last['reason']}）のあと退役まで {rt - last['t']} か月"
        else:
            note = f"入場なしで退役（限界の {due_in} か月前）"
        rows.append({"esn": s["esn"], "in_window_plan": s["from_plan"], "retire_t": rt, "retire": month_label(start, rt) if rt is not None else None,
                     "visits": len(chain), "spend_k": sum(c["cost_k"] for c in chain), "chain": s["chain"],
                     "residual_llp_cycles": int(llp_left), "residual_run_months": round(run_left, 1), "residual_value_k": round(resid_k),
                     "green_time": bool(rt is not None and run_left > ph.run_cycles / ph.cpm * 0.5),
                     "last_visit": last, "last_visit_to_exit_months": (rt - last["t"]) if (last and rt is not None) else None,
                     "heavy_late": bool(last and rt is not None and last["ws"] in ("CORE", "FULL") and rt - last["t"] < 24),
                     "due_in_at_exit": due_in, "note": note})
    labels = [month_label(start, t) for t in range(end)]
    years = sorted({l[:4] for l in labels})
    by_year = []
    for y in years:
        vs = [v for v in visits if v["label"].startswith(y)]
        ret = [r for r in rows if r["retire"] and r["retire"].startswith(y)]
        absorbed = sum(1 for r in ret if r["due_in_at_exit"] is not None and r["due_in_at_exit"] < 12)
        n_unknown = sum(1 for v in vs if not eng[v["esn"]]["from_plan"])
        if len(vs) == 0 and absorbed:
            note = f"入場 0：限界が近い {absorbed} 基を退役で吸収（入場の代わりに退役）"
        elif len(vs) == 0:
            note = "入場 0：限界に達する機がない" + ("" if y > labels[0][:4] else "")
        elif n_unknown >= len(vs) * 0.6:
            note = f"入場 {len(vs)}：うち {n_unknown} 基は窓の外の機（{'シミュレーションの状態から' if state_source == 'simulation' else '状態は非公表の仮定で、限界がこの年に固まる'}）" + (f"。退役で {absorbed} 基を吸収" if absorbed else "")
        else:
            note = f"入場 {len(vs)}" + (f"、退役で {absorbed} 基を吸収" if absorbed else "")
        by_year.append({"year": y, "visits": len(vs), "by_ws": {ws: sum(1 for v in vs if v["ws"] == ws) for ws in ("PR", "CORE", "FULL")},
                        "spend_k": sum(v["cost_k"] for v in vs), "retired": len(ret), "absorbed": absorbed, "unknown_state_visits": n_unknown,
                        "engines": sum(1 for r in rows if r["retire_t"] is None or r["retire"] >= f"{y}-12"), "note": note})
    tot_spend = sum(r["spend_k"] for r in rows)
    tot_resid = sum(r["residual_value_k"] for r in rows if r["retire_t"] is not None)
    return {"policy": policy, "start": start, "end_t": end, "end": month_label(start, end - 1), "labels": labels,
            "exits": [month_label(start, x) for x in exits], "window_months": W, "engines": rows, "by_year": by_year,
            "totals": {"engines": len(rows), "visits": len(visits), "spend_k": tot_spend, "residual_value_k": tot_resid,
                       "after_window_visits": sum(1 for v in visits if v["t"] >= W), "after_window_spend_k": sum(v["cost_k"] for v in visits if v["t"] >= W),
                       "green_time_engines": sum(1 for r in rows if r["green_time"]), "heavy_late_engines": sum(1 for r in rows if r["heavy_late"]),
                       "plan_gaps": sum(1 for r in rows for c in r["chain"] if c.get("gap")),
                       "plan_gap_max_months": max((c["slack_months"] or 0 for r in rows for c in r["chain"] if c.get("gap")), default=0), "retired": sum(1 for r in rows if r["retire_t"] is not None)},
            "physics": {"cycles_per_month": ph.cpm, "run_cycles": ph.run_cycles, "restore": ph.restore, "llp_life": ph.life, "prices": price},
            "retire_order": retire_order,
            "ops": ops,
            "ops_summary": {"thin": min(ops, key=lambda o: o["margin"]) if ops else None, "months_short": sum(1 for o in ops if o["margin"] < 0),
                            "note": "運航側：必要なエンジン数 = 2 × 飛ぶ機数（運航指数 × 必要機数、機体整備で止まる機を引く）。窓の中は計画の系列、窓の後は退役後の機数で按分。余力 = 稼働可能 − 必要 − 予備"},
            "state_source": state_source,
            "caveats": [(f"窓の外の {n_extra} 基の状態は 20 年シミュレーション（最初の 5 年は捨てる）の続きから。実機の EGT・LLP ではない"
                         if state_source == "simulation" else f"窓の外の {n_extra} 基は状態が非公表。翼上寿命の 5〜60% を飛んだと一様に仮定（限界が固まる）"),
                        "退役順「次に入場が近い機から」は、限界の近い機を入場させずに退役させる。空の年は退役が入場を吸収した年",
                        f"窓の中は凍結した計画の運航系列（必要なエンジン数・予備）を守り、余った機も手放さない（部品取りは計画側の判断）。窓の後は移行で空いた分を月 {EXIT_RATE} 基まで手放す",
                        "劣化は機ごとの係数つきの平均（月ごとの乱れなし）。計画外の取卸しは入れていない"]}


def build(cid: str, baseline_path: Path | None = None, seed: int = 11) -> dict:
    cfg, b, fleet, shops = load_inputs(cid, baseline_path)
    # pass 1: exits under the main policy give each engine its expected exit; pass 2 sizes the
    # run-out workscopes against that exit
    first = simulate(cfg, b, fleet, shops, "next_due", seed)
    hint = {r["esn"]: r["retire_t"] for r in first["engines"] if r["retire_t"] is not None}
    main = simulate(cfg, b, fleet, shops, "next_due", seed, exit_hint=hint)
    alt = {}
    for pol in POLICIES:
        if pol == "next_due":
            continue
        s = simulate(cfg, b, fleet, shops, pol, seed, exit_hint=hint)
        alt[pol] = {k: s["totals"][k] for k in ("visits", "spend_k", "residual_value_k", "green_time_engines", "heavy_late_engines", "after_window_visits")}
    naive = simulate(cfg, b, fleet, shops, "next_due", seed)     # no run-out sizing: stub rule after the window
    main["policies"] = {"next_due": {k: main["totals"][k] for k in ("visits", "spend_k", "residual_value_k", "green_time_engines", "heavy_late_engines", "after_window_visits")}, **alt}
    main["without_runout"] = {k: naive["totals"][k] for k in ("visits", "spend_k", "residual_value_k", "heavy_late_engines")}
    # the new type's deliveries slip: the 737-800s fly longer than the run-out sized for, so
    # engines planned to leave need one more visit; the run-out workscopes are NOT re-sized
    # (the plan was made against the original exits), which is the cost of the surprise
    main["delivery_delay"] = {}
    for d in DELIVERY_DELAYS:
        sd = simulate(cfg, b, fleet, shops, "next_due", seed, exit_hint=hint, delivery_delay=d)           # surprise: sized for the old exits
        hint_d = {k: v + d for k, v in hint.items()}
        sk = simulate(cfg, b, fleet, shops, "next_due", seed, exit_hint=hint_d, delivery_delay=d)         # known in time: re-sized
        newly = [e["esn"] for e in sd["engines"] if e["visits"] > next((m["visits"] for m in main["engines"] if m["esn"] == e["esn"]), 0)]
        main["delivery_delay"][str(d)] = {"months": d, "end": sd["end"], "visits": sd["totals"]["visits"], "spend_k": sd["totals"]["spend_k"],
                                          "extra_visits": sd["totals"]["visits"] - main["totals"]["visits"], "extra_spend_k": sd["totals"]["spend_k"] - main["totals"]["spend_k"],
                                          "engines_with_extra_visit": newly[:30], "months_short": sd["ops_summary"]["months_short"],
                                          "residual_value_k": sd["totals"]["residual_value_k"],
                                          "known": {"visits": sk["totals"]["visits"], "extra_visits": sk["totals"]["visits"] - main["totals"]["visits"],
                                                    "extra_spend_k": sk["totals"]["spend_k"] - main["totals"]["spend_k"], "months_short": sk["ops_summary"]["months_short"]}}
    main["delivery_delay"]["note"] = ("受領遅れ：新機の受領が遅れると退役も遅れ、退役まで持つ最軽の範囲で済ませた機が飛び続けて追加の入場が要る。"
                                      "「不意打ち」は整備範囲を当初の退役日で決めたまま、「分かってから直す」は遅れを知って整備範囲を決め直した場合。差が、受領の見通しを早く知る価値")
    main["company"] = cid
    main["note"] = ("合成データ。平均の劣化物理（companies.json の wear）で退役まで決定論的に飛ばす。退役の間隔は no_source。"
                    "窓の中は凍結した計画の入場、窓の後は退役まで持つ最軽の整備範囲。価値は mx4_params のハーフライフ換算")
    return main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args(argv)
    out = build(a.company, a.baseline, a.seed)
    p = a.out or HERE / "runout" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    T = out["totals"]
    print(f"{a.company}: {T['engines']} engines to {out['end']}, {T['visits']} visits ({T['after_window_visits']} after the window), "
          f"spend {T['spend_k'] / 1000:,.0f} M$, residual at exit {T['residual_value_k'] / 1000:,.1f} M$, green-time {T['green_time_engines']}, heavy-late {T['heavy_late_engines']}, gaps {T['plan_gaps']}")
    for pol, v in out["policies"].items():
        print(f"  {pol:9s} visits {v['visits']:4d} spend {v['spend_k'] / 1000:8,.0f} residual {v['residual_value_k'] / 1000:7,.1f} green {v['green_time_engines']:3d} heavy-late {v['heavy_late_engines']:3d}")
    w = out["without_runout"]
    print(f"  no run-out sizing: visits {w['visits']} spend {w['spend_k'] / 1000:,.0f} residual {w['residual_value_k'] / 1000:,.1f} heavy-late {w['heavy_late_engines']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
