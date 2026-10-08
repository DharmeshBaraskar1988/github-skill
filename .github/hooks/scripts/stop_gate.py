#!/usr/bin/env python3
"""
agentStop / subagentStop hook: forces another turn while an open API-catalogue run has not
passed validation. This is the enforced version of the "loop until validation passes" rule.

- No open run markers (.api-catalog-runs/*.json)  -> allow.
- validation.json missing or status != pass        -> block, reason = top errors + fix hints.
- After maxIterations forced continuations          -> allow, marker flagged gaveUp (agent must report failure).
- Markers older than 12 hours are ignored.
"""
import json
import sys
import time
from pathlib import Path

RUNS = Path(".api-catalog-runs")


def max_iterations() -> int:
    cfg = Path("api-catalog.config.yaml")
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("maxIterations:"):
                try:
                    return int(line.split(":", 1)[1].split("#")[0].strip())
                except ValueError:
                    pass
    return 5


def main():
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001
        pass
    if not RUNS.exists():
        print("{}")
        return
    limit = max_iterations()
    reasons = []
    for p in sorted(RUNS.glob("*.json")):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if time.time() - run.get("started", 0) > 12 * 3600 or run.get("gaveUp"):
            continue
        v = Path(run["dir"]) / "validation.json"
        if v.exists():
            rep = json.loads(v.read_text(encoding="utf-8"))
            if rep.get("status") == "pass":
                continue
            errs = rep.get("errors", [])[:6]
            detail = "; ".join(f"{e.get('code')} {e.get('message')} -> {e.get('fix')}" for e in errs)
        else:
            detail = "validator has not been run for this output yet"
        if run.get("blocks", 0) >= limit:
            run["gaveUp"] = True
            p.write_text(json.dumps(run), encoding="utf-8")
            continue
        run["blocks"] = run.get("blocks", 0) + 1
        p.write_text(json.dumps(run), encoding="utf-8")
        reasons.append(f"[{run.get('skill')}] {run['dir']} is not validated (attempt {run['blocks']}/{limit}): {detail}")
    if reasons:
        print(json.dumps({"decision": "block", "reason":
                          "Validation gate: continue the fix -> rebuild -> validate loop before finishing. "
                          + " | ".join(reasons)
                          + " | If it truly cannot pass, report the open errors to the user and run catalog_run.py end."}))
    else:
        print("{}")


if __name__ == "__main__":
    main()
