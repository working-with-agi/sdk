#!/usr/bin/env python3
"""Build the plan-tracking page: for each set of actuals, which candidate plan we are
following, which assumed world the actuals point to, and whether switching now pays --
month by month, so the page can step through time.

  python track.py actuals --baseline baselines/jal-2026-10.json --truth backlog --out data/jal/actuals_backlog.json
  python build_track.py --html-out track.html      # JAL and ANA, two sets of actuals each
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import track

HERE = Path(__file__).resolve().parent
COMPANIES = ("jal", "ana")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", metavar="BASELINE:ACTUALS",
                    help="baseline and actuals file pairs (default: JAL and ANA, two sets of actuals each)")
    ap.add_argument("--html-out", type=Path, default=Path("track.html"))
    args = ap.parse_args(argv)
    pairs = [tuple(x.split(":", 1)) for x in args.set] if args.set else [
        (f"baselines/{c}-2026-10.json", f"data/{c}/actuals_{w}.json") for c in COMPANIES for w in ("backlog", "crunch")]
    runs, count = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for i, (bl, a) in enumerate(pairs):
            out = Path(tmp) / f"t{i}.json"
            track.main(["status", "--baseline", str(HERE / bl), "--actuals", str(HERE / a), "--json-out", str(out)])
            d = json.loads(out.read_text(encoding="utf-8"))
            name = d.get("company", {}).get("name") or Path(bl).stem
            count[name] = count.get(name, 0) + 1
            runs.append({"title": f"{name}：実績 {chr(64 + count[name])}（{d['actuals']['as_of']} まで）", "data": d})
    html = (HERE / "track_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(runs, ensure_ascii=False, separators=(",", ":"), default=float))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(runs)} runs -> {args.html_out} ({len(html) // 1024} KB)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
