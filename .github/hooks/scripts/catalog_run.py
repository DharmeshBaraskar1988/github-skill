#!/usr/bin/env python3
"""
Run markers for the API-catalogue validation gate.

  python .github/hooks/scripts/catalog_run.py start --skill api-discovery --dir api-catalog/discovery/EU/claims
  python .github/hooks/scripts/catalog_run.py end   --dir api-catalog/discovery/EU/claims
  python .github/hooks/scripts/catalog_run.py status

While a run is open, the agentStop hook (stop_gate.py) refuses to let the agent finish until the
run's validation.json says "pass" (up to maxIterations forced continuations).
Markers live in .api-catalog-runs/ (add it to .gitignore).
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

RUNS = Path(".api-catalog-runs")


def key(d: str) -> Path:
    return RUNS / (hashlib.sha1(str(Path(d).resolve()).encode()).hexdigest()[:16] + ".json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["start", "end", "status"])
    ap.add_argument("--skill", default="")
    ap.add_argument("--dir", default="")
    a = ap.parse_args()
    RUNS.mkdir(exist_ok=True)
    if a.action == "start":
        key(a.dir).write_text(json.dumps({"skill": a.skill, "dir": str(Path(a.dir).resolve()),
                                          "started": time.time(), "blocks": 0}), encoding="utf-8")
        print(f"run started: {a.skill} -> {a.dir}")
    elif a.action == "end":
        p = key(a.dir)
        if p.exists():
            p.unlink()
        print(f"run ended: {a.dir}")
    else:
        for p in RUNS.glob("*.json"):
            r = json.loads(p.read_text(encoding="utf-8"))
            v = Path(r["dir"]) / "validation.json"
            st = json.loads(v.read_text(encoding="utf-8")).get("status") if v.exists() else "not validated"
            print(f"{r['skill']:15} {st:14} blocks={r['blocks']} {r['dir']}")


if __name__ == "__main__":
    main()
