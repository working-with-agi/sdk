#!/usr/bin/env bash
# Rebuild everything from the inputs: fleets -> baselines -> comparisons -> tracking -> roll ->
# history -> investment -> multi-fleet -> shop response -> reports. Outputs go to $OUT.
#   OUT=/tmp/out ./run_all.sh
set -euo pipefail
cd "$(dirname "$0")"
OUT="${OUT:-out}"
mkdir -p "$OUT/deltas" "$OUT/hist" "$OUT/roll" "$OUT/multi" "$OUT/shop_response" "$OUT/track"
log() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*"; }

log "fleets"; python3 company.py jal ana --all-fleets
for co in jal ana; do
  log "freeze $co"; python3 baseline.py freeze --company $co --out baselines/$co-2026-10.json
  for f in 787 767; do python3 baseline.py freeze --fleet data/$co/$f/fleet.json --shops data/$co/$f/shops.json --out baselines/$co-$f-2026-10.json --scenarios 40 --time-limit 90; done
  log "compare $co"; python3 baseline.py compare --baseline baselines/$co-2026-10.json --json-out "$OUT/deltas/$co-deltas.json"
  for w in backlog crunch; do
    python3 track.py actuals --baseline baselines/$co-2026-10.json --truth $w --out data/$co/actuals_$w.json
    python3 track.py status --baseline baselines/$co-2026-10.json --actuals data/$co/actuals_$w.json --json-out "$OUT/track/$co-track-$w.json"
  done
  log "roll $co"; python3 roll.py $co --out-dir "$OUT/roll"
  log "multi $co"; python3 multi.py $co --out "$OUT/multi/$co.json" --scenarios 30 --time-limit 60
  python3 shop_response.py $co --commit $([ $co = jal ] && echo 20 || echo 10) --out "$OUT/shop_response/$co.json"
done
log "history"; python3 history.py jal ana --out-dir "$OUT/hist"
log "invest"; python3 invest.py --json-out "$OUT/invest.json"
cp "$OUT/multi/"*.json multi/ 2>/dev/null || true
log "reports"
python3 build_report.py --deltas-dir "$OUT/deltas" --invest "$OUT/invest.json" --history-dir "$OUT/hist" --roll-dir "$OUT/roll" --html-out "$OUT/report.html"
python3 build_monthly.py --html-out "$OUT/monthly.html"
python3 build_annual.py --html-out "$OUT/annual.html"
python3 build_track.py --html-out "$OUT/track.html"
log "tests"; python3 -m unittest discover -s tests 2>&1 | tail -3 || true
log "done -> $OUT"
