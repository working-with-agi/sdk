#!/usr/bin/env bash
# Rebuild everything from the inputs: fleets -> baselines -> comparisons -> tracking -> roll ->
# history -> investment -> multi-fleet -> shop response -> reports. Outputs go to $OUT.
#   OUT=/tmp/out ./run_all.sh            # REVIEW_NO_AI=1 skips the Claude call in review.py
set -euo pipefail
cd "$(dirname "$0")"
OUT="${OUT:-out}"
mkdir -p "$OUT/deltas" "$OUT/hist" "$OUT/roll" "$OUT/multi" "$OUT/shop_response" "$OUT/track" "$OUT/runout" "$OUT/review" "$OUT/demand" "$OUT/backtest"
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
for co in jal ana; do
  log "runout $co"; python3 runout.py $co --out "$OUT/runout/$co.json"
  log "demand $co"; python3 demand.py $co --runout "$OUT/runout/$co.json" --out "$OUT/demand/$co.json"
  python3 plan_from_demand.py $co --out "$OUT/demand/$co-plan.json" --scenarios 40 --time-limit 90
  log "backtest $co"; python3 backtest.py $co --out "$OUT/backtest/$co.json"
  log "review $co"; python3 review.py $co --track "$OUT/track/$co-track-crunch.json" --roll "$OUT/roll/$co-roll-2027-10.json" --runout "$OUT/runout/$co.json" --history "$OUT/hist/$co-history.json" --plan-from-demand "$OUT/demand/$co-plan.json" --backtest "$OUT/backtest/$co.json" --out "$OUT/review/$co.json" ${REVIEW_NO_AI:+--no-ai}
done
cp "$OUT/runout/"*.json runout/ 2>/dev/null || true; cp "$OUT/review/"*.json review/ 2>/dev/null || true; cp "$OUT/demand/"*.json demand/ 2>/dev/null || true; cp "$OUT/backtest/"*.json backtest/ 2>/dev/null || true
cp "$OUT/multi/"*.json multi/ 2>/dev/null || true
log "reports"
python3 build_report.py --deltas-dir "$OUT/deltas" --invest "$OUT/invest.json" --history-dir "$OUT/hist" --roll-dir "$OUT/roll" --runout-dir "$OUT/runout" --review-dir "$OUT/review" --demand-dir "$OUT/demand" --backtest-dir "$OUT/backtest" --html-out "$OUT/report.html"
python3 build_monthly.py --html-out "$OUT/monthly.html"
python3 build_annual.py --html-out "$OUT/annual.html"
python3 build_track.py --html-out "$OUT/track.html"
log "tests"; python3 -m unittest discover -s tests 2>&1 | tail -3 || true
log "done -> $OUT"
