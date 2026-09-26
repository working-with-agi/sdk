#!/usr/bin/env python3
"""Build the plan-tracking page: for each set of actuals, which candidate plan we are
following, which assumed world the actuals point to, and whether switching now pays --
month by month, so the page can step through time.

  python track.py actuals --truth backlog --out data/actuals_backlog.json
  python track.py actuals --truth crunch  --out data/actuals_crunch.json
  python build_track.py --html-out track.html      # runs track.py status for each file
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import track

HERE = Path(__file__).resolve().parent
DEFAULT = [HERE / "data" / "actuals_backlog.json", HERE / "data" / "actuals_crunch.json"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--actuals", type=Path, nargs="+", default=DEFAULT)
    ap.add_argument("--baseline", type=Path, default=HERE / "baselines" / "2026-10.json")
    ap.add_argument("--html-out", type=Path, default=Path("track.html"))
    args = ap.parse_args(argv)
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, a in enumerate(args.actuals):
            out = Path(tmp) / f"t{i}.json"
            track.main(["status", "--baseline", str(args.baseline), "--actuals", str(a), "--json-out", str(out)])
            d = json.loads(out.read_text(encoding="utf-8"))
            runs.append({"title": f"実績 {chr(65 + i)}（{d['actuals']['as_of']} まで）", "data": d})
    html = (HERE / "track_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(runs, ensure_ascii=False, separators=(",", ":"), default=float))
    args.html_out.write_text(html, encoding="utf-8")
    print(f"{len(runs)} runs -> {args.html_out} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
