#!/usr/bin/env python3
"""Build the what-if explorer: move the conditions nobody can pin down and see, instantly,
which actions the optimiser picks and what that does to cost and AOG risk. Answers come
from precomputed optimisation runs (explore.py, sensitivity.py), so the page needs no
server; an AI button explains the current setting.

  python build_whatif.py --explore explore.json --sensitivity sensitivity.json \\
                         --baseline baselines/2026-10.json --html-out whatif.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--explore", type=Path, default=Path("explore.json"))
    ap.add_argument("--sensitivity", type=Path, default=Path("sensitivity.json"))
    ap.add_argument("--baseline", type=Path, default=HERE / "baselines" / "2026-10.json")
    ap.add_argument("--html-out", type=Path, default=Path("whatif.html"))
    args = ap.parse_args(argv)
    ex = json.loads(args.explore.read_text(encoding="utf-8"))
    runs = [{"f": r["f"], "ok": r["feasible"], "pattern": r["pattern"], "mean": round(r.get("mean", 0)),
             "p90": round(r.get("p90", 0)), "aog": r.get("aog_prob", 0), "swaps": r.get("swaps", 0),
             "kits": r.get("kits", 0), "spares": r.get("spares", 0), "early": r.get("early_months", 0),
             "external": r.get("external_share", 0)} for r in ex["runs"]]
    data = {"factors": ex["factors"], "labels": ex["labels"], "rules": ex["rules"], "runs": runs}
    if args.sensitivity.exists():
        sr = json.loads(args.sensitivity.read_text(encoding="utf-8"))["runs"]
        data["breakeven"] = [{"price": r["f"]["midlife"], "swaps": r["swaps"], "mean": round(r["mean"])}
                             for r in sr if r["kind"] == "breakeven" and r["feasible"]]
        data["coupling"] = [{"owned": r["owned"], "value": r["f"]["value"], "sub": r["f"]["substitute"],
                             "aog": r.get("aog_prob"), "mean": round(r.get("mean", 0)), "early": r.get("early_months")}
                            for r in sr if r["kind"] == "coupling" and r["feasible"]]
    if args.baseline.exists():
        b = json.loads(args.baseline.read_text(encoding="utf-8"))
        data["baseline"] = {"version": b["version"], "cost": round(b["plan_of_record"]["total_cost"]),
                            "aog": b["plan_of_record"]["aog_prob"], "visits": b["plan_of_record"]["shop_visits"]}
    html = (HERE / "whatif_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(runs)} runs -> {args.html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
