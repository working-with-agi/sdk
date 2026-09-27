"""Topic threads (話題ごとの分離): every finding, assumption, action, exception and screen
is routed into one topic, so a meeting can take the agenda one thread at a time.

Routing is mechanical: an item goes to the topic whose framework key it names, else to
the topic whose words it mentions most, else to "method". The output is the generic shape
Secretary.io's topic threads would take (topic, items by kind, status, owner, screens),
fed here from the engine-plan component's own outputs.

  python topics.py jal --review out/review/jal.json --playbook out/playbook/jal.json --track out/track/jal-track-crunch.json --out out/topics/jal.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEV = {"crit": 0, "warn": 1, "info": 2, "ok": 3}


def load_defs() -> dict:
    return json.loads((HERE / "data" / "topics.json").read_text(encoding="utf-8"))


def route(text: str, defs: dict, key: str | None = None) -> str:
    if key:
        for t in defs["topics"]:
            if key in t["framework_keys"] or key in t.get("playbook", []):
                return t["id"]
    best, score = "method", 0
    for t in defs["topics"]:
        n = sum(text.count(w) for w in t["words"])
        if n > score:
            best, score = t["id"], n
    return best


def build(cid: str, review: dict | None, playbook: dict | None, track: dict | None) -> dict:
    defs = load_defs()
    threads = {t["id"]: {**{k: t[k] for k in ("id", "name", "what", "owner", "views")}, "assumptions": [], "findings": [], "actions": [], "exceptions": [], "triggers": []} for t in defs["topics"]}
    if review:
        fw = review.get("framework") or {}
        for a in fw.get("table", []):
            threads[route(a["name"], defs, a["key"])]["assumptions"].append({k: a[k] for k in ("key", "name", "cadence_months", "trigger", "last_derived", "status", "owner")})
        for f in fw.get("fired", []):
            threads[route(f["name"], defs, f["key"])]["triggers"].append({"name": f["name"], "evidence": f["evidence"]})
        for s in review.get("symptoms", []):
            m = re.search(r"前提「(.+?)」", s["finding"])
            key = None
            if m:
                key = next((a["key"] for a in fw.get("table", []) if a["name"] == m.group(1)), None)
            threads[route(s["finding"] + s["evidence"] + s["ask"], defs, key)]["findings"].append({k: s[k] for k in ("loop", "stage", "severity", "finding", "ask")})
    if playbook:
        for st in playbook["steps"][1:]:
            tid = route(st["label"], defs, st["key"])
            d = st.get("delta_vs_base", {})
            threads[tid]["actions"].append({"key": st["key"], "label": st["label"], "who": st["who"], "when": st["when"], "deadline": st["deadline"], "trigger": st["trigger"],
                                            "expected_delta_k": d.get("total_cost"), "aog_delta_pt": (d.get("aog_prob") or 0) * 100})
    if track:
        for x in track["timeline"]:
            for e in x["exceptions"]:
                threads[route(e["kind"] + e["detail"], defs)]["exceptions"].append({"as_of": x["as_of"], "esn": e["esn"], "kind": e["kind"], "detail": e["detail"]})
    out = []
    for t in threads.values():
        worst = min((f["severity"] for f in t["findings"]), key=SEV.get, default=None)
        status = "crit" if worst == "crit" or any(a["status"] == "overdue" for a in t["assumptions"]) else "warn" if worst == "warn" or t["triggers"] else "info" if t["findings"] or t["exceptions"] else "ok"
        t["status"] = status
        t["counts"] = {"assumptions": len(t["assumptions"]), "findings": len(t["findings"]), "actions": len(t["actions"]), "exceptions": len(t["exceptions"]), "triggers": len(t["triggers"])}
        t["findings"].sort(key=lambda f: SEV[f["severity"]])
        t["exceptions"] = t["exceptions"][-12:]
        out.append(t)
    order = {"crit": 0, "warn": 1, "info": 2, "ok": 3}
    out.sort(key=lambda t: (order[t["status"]], -t["counts"]["findings"]))
    unrouted = 0
    return {"company": cid, "threads": out, "note": defs["note"], "unrouted": unrouted}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company")
    ap.add_argument("--review", type=Path)
    ap.add_argument("--playbook", type=Path)
    ap.add_argument("--track", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None  # noqa: E731
    out = build(a.company, load(a.review), load(a.playbook), load(a.track))
    p = a.out or HERE / "topics" / f"{a.company}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in out["threads"]:
        c = t["counts"]
        print(f"{a.company} [{t['status']}] {t['name']}: 前提 {c['assumptions']}, 指摘 {c['findings']}, 打ち手 {c['actions']}, 例外 {c['exceptions']}, 引き金 {c['triggers']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
