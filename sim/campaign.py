"""Run randomised trials for a variant in parallel and write results/<variant>/<pill>.json.

    python -m sim.campaign v0_original --pills iron small caplet cap0 --trials 200
"""
from __future__ import annotations

import argparse
import collections
import importlib
import json
import multiprocessing as mp
import os
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _one(args):
    variant, pill, seed, cycles = args
    from sim.engine import run_trial
    mod = importlib.import_module(f"sim.variants.{variant}")
    dbg: list = []
    try:
        r = run_trial(mod.spec, pill, seed, cycles=cycles, debug=dbg)
    except Exception as exc:  # a crashed trial is reported, never silently dropped
        return dict(seed=seed, error=repr(exc))
    d = asdict(r)
    d.pop("frames", None)
    d["passed"] = r.passed
    d["anomalies"] = len(dbg)
    d["first_anomaly"] = dbg[0] if dbg else None
    return d


def summarize(trials: list) -> dict:
    out = collections.Counter()
    sites = collections.Counter()
    n_cycles = 0
    for t in trials:
        if "error" in t:
            out["error"] += 1
            continue
        if t["leak"]:
            out["leak"] += 1
        for c in t["cycles"]:
            out[c["outcome"]] += 1
            n_cycles += 1
            if c["outcome"] == "jam":
                sites[c["jam_site"]] += 1
    ok_trials = sum(1 for t in trials if t.get("passed"))
    jam_trials = sum(1 for t in trials if any(c["outcome"] == "jam" for c in t.get("cycles", [])))
    return dict(trials=len(trials), passed_trials=ok_trials, cycles=n_cycles,  # "empty" = hopper already empty (after a double/loss)
                outcomes=dict(out), jam_sites=dict(sites),
                jam_rate_per_trial=jam_trials / max(len(trials), 1),
                anomaly_trials=sum(1 for t in trials if t.get("anomalies")),
                unstable_trials=sum(1 for t in trials if t.get("sim_unstable")),
                errors=sum(1 for t in trials if "error" in t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variant")
    ap.add_argument("--pills", nargs="+", default=["iron", "small", "caplet", "cap0"])
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    outdir = ROOT / "results" / (a.variant + (f"_{a.tag}" if a.tag else ""))
    outdir.mkdir(parents=True, exist_ok=True)
    # warm the convex-decomposition cache once before forking workers
    importlib.import_module(f"sim.variants.{a.variant}").spec(a.pills[0])
    with mp.get_context("fork").Pool(a.workers) as pool:
        for pill in a.pills:
            t0 = time.time()
            jobs = [(a.variant, pill, a.seed0 + k, a.cycles) for k in range(a.trials)]
            trials = []
            for k, r in enumerate(pool.imap_unordered(_one, jobs)):
                trials.append(r)
                if (k + 1) % 25 == 0:
                    s = summarize(trials)
                    json.dump(dict(variant=a.variant, pill=pill, partial=True, summary=s,
                                   trials=sorted(trials, key=lambda t: t["seed"])),
                              open(outdir / f"{pill}.partial.json", "w"), indent=1, default=float)
                    print(f"[{a.variant}/{pill}] {k + 1}/{a.trials} {s['outcomes']} "
                          f"{time.time() - t0:.0f}s", flush=True)
            trials.sort(key=lambda t: t["seed"])
            s = summarize(trials)
            json.dump(dict(variant=a.variant, pill=pill, summary=s, trials=trials),
                      open(outdir / f"{pill}.json", "w"), indent=1, default=float)
            (outdir / f"{pill}.partial.json").unlink(missing_ok=True)
            print(f"== {a.variant}/{pill}: {json.dumps(s)}", flush=True)


if __name__ == "__main__":
    main()
