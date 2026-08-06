#!/usr/bin/env python3
"""One command for the whole validation sweep: static, live labs, and the app.

Stages, in order:
  1. static     validate_workshop.py     (compiles, structure, stale facts, secrets)
  2. reset      reset_lab_state.py       (clean slate so the run is repeatable)
  3. labs       run_labs_live.py         (execute every lab, assert it worked)
  4. app        validate_app.py          (assert the app reflects the lab results)

Usage:
  python scripts/validate_all.py                 # full sweep
  python scripts/validate_all.py --fast          # skip the slow labs
  python scripts/validate_all.py --twice         # prove repeatability
  python scripts/validate_all.py --skip-reset
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import harness_common as h

# Labs whose provisioning waits dominate the sweep; --fast omits them.
SLOW_LABS = ("backup", "reverse_etl", "feature_store", "branches")


def stage(title: str, argv: list[str]) -> tuple[int, float]:
    h.say(f"\n{h.C.B}══ {title} {'═' * max(0, 38 - len(title))}{h.C.X}")
    h.say(f"{h.C.DIM}$ {' '.join(argv)}{h.C.X}")
    started = time.time()
    proc = subprocess.run([sys.executable, *argv], cwd=h.REPO)
    return proc.returncode, time.time() - started


def latest(name: str) -> dict | None:
    path = h.REPORT_DIR / f"{name}-latest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None


def snapshot_statuses(report: dict | None) -> dict[str, str]:
    if not report:
        return {}
    return {r["id"]: r["status"] for r in report.get("results", [])}


def compare_runs(first: dict[str, str], second: dict[str, str]) -> list[str]:
    drift: list[str] = []
    for lab in sorted(set(first) | set(second)):
        a, b = first.get(lab, "(absent)"), second.get(lab, "(absent)")
        if a != b:
            drift.append(f"{lab}: run 1 = {a}, run 2 = {b}")
    return drift


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full workshop validation sweep.")
    ap.add_argument("--profile", help="Databricks CLI profile")
    ap.add_argument("--target", default="dev", help="bundle target")
    ap.add_argument("--only", help="comma-separated lab ids for the live stage")
    ap.add_argument("--fast", action="store_true", help=f"skip slow labs ({', '.join(SLOW_LABS)})")
    ap.add_argument("--skip-static", action="store_true")
    ap.add_argument("--skip-reset", action="store_true")
    ap.add_argument("--skip-labs", action="store_true")
    ap.add_argument("--skip-app", action="store_true")
    ap.add_argument("--no-deploy", action="store_true", help="skip the bundle deploy")
    ap.add_argument("--twice", action="store_true",
                    help="run reset+labs+app twice and diff the reports to prove repeatability")
    ap.add_argument("--data-api-url", default="")
    ap.add_argument("--sp-app-id", default="")
    args = ap.parse_args()

    scripts = Path("scripts")
    common: list[str] = []
    if args.profile:
        common += ["--profile", args.profile]

    outcomes: list[tuple[str, int, float]] = []

    if not args.skip_static:
        code, secs = stage("Static validation", [str(scripts / "validate_workshop.py")])
        outcomes.append(("static", code, secs))
        if code != 0:
            h.say(f"\n{h.C.R}Static validation failed — stopping before touching the workspace.{h.C.X}")
            return 1

    lab_statuses: list[dict[str, str]] = []
    passes = 2 if args.twice else 1

    for attempt in range(1, passes + 1):
        label = f" (pass {attempt}/{passes})" if passes > 1 else ""

        if not args.skip_reset:
            code, secs = stage(f"Reset lab state{label}", [str(scripts / "reset_lab_state.py"), *common])
            outcomes.append((f"reset{label}", code, secs))
            if code != 0:
                h.say(f"\n{h.C.R}Reset failed — a dirty project makes the run unrepeatable.{h.C.X}")
                return 1

        if not args.skip_labs:
            argv = [str(scripts / "run_labs_live.py"), *common, "--target", args.target]
            if args.only:
                argv += ["--only", args.only]
            elif args.fast:
                argv += ["--skip", ",".join(SLOW_LABS)]
            # The bundle only needs deploying once per sweep.
            if args.no_deploy or attempt > 1:
                argv.append("--no-deploy")
            if args.data_api_url:
                argv += ["--data-api-url", args.data_api_url]
            if args.sp_app_id:
                argv += ["--sp-app-id", args.sp_app_id]
            code, secs = stage(f"Live labs{label}", argv)
            outcomes.append((f"labs{label}", code, secs))
            lab_statuses.append(snapshot_statuses(latest("live-labs")))

        if not args.skip_app:
            code, secs = stage(f"Lab Console API{label}", [str(scripts / "validate_app.py"), *common])
            outcomes.append((f"app{label}", code, secs))

    drift: list[str] = []
    if args.twice and len(lab_statuses) == 2:
        drift = compare_runs(*lab_statuses)
        h.say(f"\n{h.C.B}══ Repeatability {'═' * 24}{h.C.X}")
        if drift:
            for line in drift:
                h.say(f"  {h.C.R}✗{h.C.X} {line}")
        else:
            h.say(f"  {h.C.G}✓{h.C.X} both passes produced identical per-lab outcomes")

    h.say(f"\n{h.C.B}── Sweep summary ───────────────────────{h.C.X}")
    for name, code, secs in outcomes:
        mark = f"{h.C.G}✓{h.C.X}" if code == 0 else f"{h.C.R}✗{h.C.X}"
        h.say(f"  {mark} {name:<22} exit={code}  {h.fmt_duration(secs)}")
    failed = [name for name, code, _ in outcomes if code != 0]
    if failed or drift:
        h.say(f"\n{h.C.R}SWEEP FAILED{h.C.X} ({', '.join(failed) or 'repeatability drift'})")
        return 1
    h.say(f"\n{h.C.G}SWEEP PASSED{h.C.X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
