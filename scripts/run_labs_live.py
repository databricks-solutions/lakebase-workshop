#!/usr/bin/env python3
"""Run every workshop lab against a real workspace and assert it actually worked.

validate_workshop.py proves the labs compile; this proves they run. Each notebook is
deployed with the bundle and executed as a serverless notebook job — the same compute
a participant uses — then three things are checked:

  1. the job reached SUCCESS
  2. every sentinel string appears in the captured cell output
  3. no "forbidden" string appears, i.e. none of the messages labs print from an
     `except` block that would otherwise let a broken lab finish green
  4. the manifest's post-conditions hold when queried independently afterwards

Usage:
  python scripts/run_labs_live.py                      # full sweep
  python scripts/run_labs_live.py --only setup,auth    # a subset
  python scripts/run_labs_live.py --from branches      # resume at a lab
  python scripts/run_labs_live.py --preflight-only     # just report configuration
  python scripts/run_labs_live.py --dry-run            # show the plan, run nothing

Exit code is 0 only when every selected lab passed. Skipped labs (missing feature
gate) do not fail the run but are reported.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import harness_common as h
import lab_manifest as manifest
from lab_manifest import Lab

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class CheckResult:
    label: str
    kind: str
    ok: bool
    detail: str = ""


@dataclass
class LabResult:
    id: str
    path: str
    status: str = PASS
    reason: str = ""
    duration_s: float = 0.0
    run_page_url: str = ""
    missing_sentinels: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)
    skipped_cells: list[str] = field(default_factory=list)
    retried: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    failed_cell: str = ""
    error: str = ""
    stdout_tail: str = ""


# --------------------------------------------------------------------------- #
# SDK post-condition handlers
# --------------------------------------------------------------------------- #
def _check_project_exists(ctx: h.Ctx, _arg: str) -> tuple[bool, str]:
    try:
        ctx.w.postgres.get_project(name=ctx.project_name())
        return True, ctx.project_id
    except Exception as e:
        return False, str(e)[:200]


def _check_endpoint_ready(ctx: h.Ctx, branch: str) -> tuple[bool, str]:
    """Ready means past provisioning. IDLE is healthy: it wakes on connect."""
    try:
        ep = h.endpoint_for(ctx, branch)
    except Exception as e:
        return False, str(e)[:200]
    if ep is None:
        return False, f"branch {branch!r} has no endpoint"
    state = str(getattr(ep.status, "current_state", "")).upper()
    ready = any(s in state for s in ("ACTIVE", "IDLE", "DEGRADED"))
    return ready, state.split(".")[-1]


def _check_branch_exists(ctx: h.Ctx, branch: str) -> tuple[bool, str]:
    try:
        b = ctx.w.postgres.get_branch(name=ctx.branch_name(branch))
        return True, str(getattr(b, "name", branch))
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def _app_sp(ctx: h.Ctx) -> str | None:
    try:
        app = ctx.w.apps.get(name=ctx.app_name)
    except Exception:
        return None
    return getattr(app, "effective_service_principal_client_id", None) or app.service_principal_client_id


def _check_project_acl_has_app_sp(ctx: h.Ctx, _arg: str) -> tuple[bool, str]:
    sp = _app_sp(ctx)
    if not sp:
        return False, f"app {ctx.app_name!r} not found"
    try:
        acl = ctx.w.permissions.get(
            request_object_type="database-projects", request_object_id=ctx.project_id
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    for entry in acl.access_control_list or []:
        if entry.service_principal_name == sp:
            levels = [str(p.permission_level).split(".")[-1] for p in entry.all_permissions or []]
            return ("CAN_MANAGE" in levels), f"{sp} -> {levels}"
    return False, f"{sp} has no ACL entry on the project"


def _check_uc_grant_app_sp(ctx: h.Ctx, full_name: str) -> tuple[bool, str]:
    from databricks.sdk.service.catalog import SecurableType

    sp = _app_sp(ctx)
    if not sp:
        return False, f"app {ctx.app_name!r} not found"
    try:
        grants = ctx.w.grants.get(SecurableType.SCHEMA.value, full_name)
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    for assignment in grants.privilege_assignments or []:
        if assignment.principal == sp:
            privs = {str(p.value if hasattr(p, "value") else p) for p in assignment.privileges or []}
            need = {"USE_SCHEMA", "SELECT"}
            missing = need - privs
            return (not missing), f"{sp} has {sorted(privs)}"
    return False, f"{sp} has no grant on {full_name}"


def _synced_table(ctx: h.Ctx, table: str):
    return ctx.w.postgres.get_synced_table(name=f"synced_tables/{table}")


def _check_synced_table_ready(ctx: h.Ctx, table_suffix: str) -> tuple[bool, str]:
    full = f"{ctx.uc_catalog}.{ctx.uc_schema}.{table_suffix}"
    try:
        st = _synced_table(ctx, full)
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    state = str(getattr(getattr(st, "status", None), "detailed_state", "")).split(".")[-1]
    bad = any(flag in state.upper() for flag in ("FAIL", "ERROR", "OFFLINE"))
    return (bool(state) and not bad), state or "(no state reported)"


# A freshly triggered sync sits in WAITING_FOR_RESOURCES / INITIALIZING for a while;
# only these states mean the update is over and its verdict is final.
_PIPELINE_TERMINAL = ("COMPLETED", "COMPLETE", "FAILED", "CANCELED", "CANCELLED")


def _check_synced_table_pipeline_ok(ctx: h.Ctx, table_suffix: str,
                                    wait_s: int = 600) -> tuple[bool, str]:
    full = f"{ctx.uc_catalog}.{ctx.uc_schema}.{table_suffix}"
    try:
        st = _synced_table(ctx, full)
        pipeline_id = getattr(getattr(st, "status", None), "pipeline_id", None)
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    if not pipeline_id:
        return False, "synced table reports no pipeline_id"

    deadline = time.time() + wait_s
    state = ""
    while True:
        try:
            updates = list(ctx.w.pipelines.list_updates(pipeline_id=pipeline_id).updates or [])
        except Exception as e:
            return False, f"pipeline {pipeline_id}: {type(e).__name__}: {str(e)[:120]}"
        if not updates:
            return False, f"pipeline {pipeline_id} has no updates"
        state = str(getattr(updates[0], "state", "")).split(".")[-1].upper()
        if state in _PIPELINE_TERMINAL or time.time() > deadline:
            break
        time.sleep(20)
    ok = state in ("COMPLETED", "COMPLETE")
    suffix = "" if state in _PIPELINE_TERMINAL else f" (still running after {wait_s}s)"
    return ok, f"pipeline {pipeline_id} last update {state}{suffix}"


def _check_online_table_ok(ctx: h.Ctx, table_suffix: str) -> tuple[bool, str]:
    """A feature table published into a Lakebase project is a synced table.

    The Online Tables API refuses these outright ("no longer available for PG
    instances"), so state has to come from the synced-table API.
    """
    return _check_synced_table_ready(ctx, table_suffix)


def _check_uc_row_count(ctx: h.Ctx, arg: str) -> tuple[bool, str]:
    """arg: '<full.table.name>:<expectation>' e.g. 'main.s.t:>=12'."""
    table, _, expect = arg.rpartition(":")
    try:
        rows = list(
            ctx.w.statement_execution.execute_statement(
                statement=f"SELECT count(*) AS n FROM {table}",
                warehouse_id=_warehouse_id(ctx),
                wait_timeout="50s",
            ).result.data_array
            or []
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"
    if not rows:
        return False, "query returned no rows"
    ok, detail = h.evaluate_expect(rows[0][0], expect)
    return ok, f"{table}: {detail}"


_WAREHOUSE_CACHE: dict[str, str] = {}


def _warehouse_id(ctx: h.Ctx) -> str:
    if "id" in _WAREHOUSE_CACHE:
        return _WAREHOUSE_CACHE["id"]
    warehouses = sorted(
        ctx.w.warehouses.list(),
        key=lambda x: (str(getattr(x, "state", "")) != "RUNNING", x.name or ""),
    )
    if not warehouses:
        raise RuntimeError("no SQL warehouse available for UC row-count checks")
    _WAREHOUSE_CACHE["id"] = warehouses[0].id
    return warehouses[0].id


SDK_CHECKS = {
    "project_exists": _check_project_exists,
    "endpoint_ready": _check_endpoint_ready,
    "branch_exists": _check_branch_exists,
    "project_acl_has_app_sp": _check_project_acl_has_app_sp,
    "uc_grant_app_sp": _check_uc_grant_app_sp,
    "synced_table_ready": _check_synced_table_ready,
    "synced_table_pipeline_ok": _check_synced_table_pipeline_ok,
    "online_table_ok": _check_online_table_ok,
    "uc_row_count": _check_uc_row_count,
}


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def run_sql_file(ctx: h.Ctx, lab: Lab) -> tuple[bool, str, str]:
    """Execute a .sql lab the way a participant would: one statement at a time.

    Autocommit rather than one big transaction, because that is what a SQL editor
    does, and every statement is attempted even after one fails so a single run
    reports every broken query in the file instead of only the first.
    """
    text = (h.REPO / lab.path).read_text()
    statements = split_sql(text)
    log: list[str] = []
    failures: list[str] = []
    conn = h.pg_connect(ctx)
    conn.autocommit = True
    try:
        for stmt in statements:
            head = " ".join(stmt.split())[:80]
            with conn.cursor() as cur:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    first = str(e).strip().splitlines()[0]
                    failures.append(f"{head} -> {first}")
                    log.append(f"FAIL: {head}\n      {first}")
                    continue
            log.append(f"ok: {head}")
    finally:
        conn.close()
    if failures:
        detail = f"{len(failures)} of {len(statements)} statements failed:\n" + "\n".join(
            f"  - {f}" for f in failures
        )
        return False, detail, "\n".join(log)
    return True, "", "\n".join(log)


def split_sql(text: str) -> list[str]:
    """Split on semicolons outside strings, comments, and dollar-quoted blocks."""
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    quote: str | None = None
    dollar_tag: str | None = None
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if dollar_tag:
            if text.startswith(dollar_tag, i):
                buf.append(dollar_tag); i += len(dollar_tag); dollar_tag = None
                continue
        elif quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\":
                if nxt:
                    buf.append(nxt); i += 2; continue
            i += 1
            continue
        elif ch == "-" and nxt == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        elif ch in "'\"":
            quote = ch
        elif ch == "$":
            j = text.find("$", i + 1)
            tag_body = text[i + 1:j] if j != -1 else None
            # $$ ... $$ or $tag$ ... $tag$ — semicolons inside are not separators.
            if tag_body is not None and (tag_body == "" or tag_body.replace("_", "").isalnum()):
                dollar_tag = text[i:j + 1]
                buf.append(dollar_tag); i = j + 1
                continue
        elif ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    # BEGIN/COMMIT are handled by psycopg's own transaction, and a bare COMMIT
    # outside one is a warning we do not want in the log.
    return [s for s in statements if s.upper() not in ("BEGIN", "COMMIT", "END")]


def evaluate_checks(ctx: h.Ctx, lab: Lab) -> list[CheckResult]:
    results: list[CheckResult] = []
    ph = ctx.placeholders()
    conns: dict[str, object] = {}
    # Remember an unreachable branch: without this, every SQL check on it pays the
    # full connect-retry budget again and a single dead branch stretches the sweep.
    unreachable: dict[str, str] = {}
    try:
        for check in lab.checks:
            spec = manifest.resolve(check.spec, ph)
            if check.kind == "sql":
                try:
                    if check.branch in unreachable:
                        raise RuntimeError(unreachable[check.branch])
                    if check.branch not in conns:
                        try:
                            conns[check.branch] = h.pg_connect(ctx, check.branch)
                        except Exception as e:
                            unreachable[check.branch] = (
                                f"branch {check.branch!r} unreachable: "
                                f"{type(e).__name__}: {str(e)[:140]}"
                            )
                            raise
                    value = h.scalar(conns[check.branch], spec)
                    ok, detail = h.evaluate_expect(value, check.expect)
                except Exception as e:
                    ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
                results.append(CheckResult(check.label, f"sql[{check.branch}]", ok, detail))
            else:
                name, _, arg = spec.partition(":")
                handler = SDK_CHECKS.get(name)
                if handler is None:
                    results.append(CheckResult(check.label, "sdk", False, f"unknown handler {name!r}"))
                    continue
                try:
                    ok, detail = handler(ctx, arg)
                except Exception as e:
                    ok, detail = False, f"{type(e).__name__}: {str(e)[:180]}"
                results.append(CheckResult(check.label, "sdk", ok, detail))
    finally:
        for conn in conns.values():
            try:
                conn.close()
            except Exception:
                pass
    return results


def run_lab(ctx: h.Ctx, lab: Lab, file_path: str, params: dict[str, str]) -> LabResult:
    res = LabResult(id=lab.id, path=lab.path)
    started = time.time()

    if lab.kind == "sql":
        ok, err, log = run_sql_file(ctx, lab)
        res.duration_s = round(time.time() - started, 1)
        res.stdout_tail = log[-4000:]
        if not ok:
            res.status = FAIL
            res.reason = err.splitlines()[0]
            res.error = err
            return res
    else:
        notebook = h.workspace_notebook_path(file_path, lab.path)
        run_args = dict(run_name=f"validate-{lab.id}", params={**lab.params, **params},
                        timeout_s=lab.timeout_s)
        outcome = h.run_notebook(ctx, notebook, **run_args)
        # Serverless occasionally loses the kernel right after %pip install, which is
        # an environment flake rather than a lab defect. Give it exactly one more
        # chance so a flake cannot masquerade as a broken lab (or vice versa).
        if outcome.kernel_died:
            h.say(f"    {h.C.Y}↻{h.C.X} kernel died; retrying once")
            res.retried = True
            outcome = h.run_notebook(ctx, notebook, **run_args)
        res.duration_s = outcome.duration_s
        res.run_page_url = outcome.run_page_url
        res.error = outcome.error
        res.stdout_tail = outcome.stdout[-4000:]
        failed = outcome.failed_cell
        if failed is not None:
            res.failed_cell = f"cell {failed.position:g}: {failed.first_line[:120]}"
        if outcome.timed_out:
            res.status = FAIL
            res.reason = f"timed out after {h.fmt_duration(lab.timeout_s)} (run cancelled)"
            return res
        if not outcome.succeeded:
            res.status = FAIL
            res.reason = f"job {outcome.result_state or outcome.life_cycle_state}"
            return res
        # A run can report SUCCESS after the kernel dies mid-notebook, leaving every
        # later cell unexecuted. Name that directly instead of reporting it as a pile
        # of missing sentinels.
        skipped = outcome.skipped_code_cells
        if outcome.kernel_died or skipped:
            res.status = FAIL
            res.skipped_cells = [f"cell {c.position:g}: {c.first_line[:100]}" for c in skipped]
            cause = "the Python kernel died" if outcome.kernel_died else "the notebook aborted"
            res.reason = (f"{cause} — {len(skipped)} code cell(s) never ran "
                          f"(the job still reported SUCCESS)")
            return res

        stdout = outcome.stdout
        res.missing_sentinels = [s for s in lab.sentinels if s not in stdout]
        res.forbidden_hits = [s for s in lab.forbidden if s in stdout]
        if res.missing_sentinels or res.forbidden_hits:
            res.status = FAIL
            bits = []
            if res.missing_sentinels:
                bits.append(f"{len(res.missing_sentinels)} sentinel(s) missing")
            if res.forbidden_hits:
                bits.append(f"{len(res.forbidden_hits)} swallowed failure(s)")
            res.reason = ", ".join(bits)

    res.checks = evaluate_checks(ctx, lab)
    failed_checks = [c for c in res.checks if not c.ok]
    if failed_checks:
        res.status = FAIL
        extra = f"{len(failed_checks)} post-condition(s) failed"
        res.reason = f"{res.reason}; {extra}" if res.reason else extra
    return res


# --------------------------------------------------------------------------- #
# Selection + reporting
# --------------------------------------------------------------------------- #
def select_labs(args) -> list[Lab]:
    labs = list(manifest.RUN_ORDER)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = wanted - set(manifest.LABS_BY_ID)
        if unknown:
            h.say(f"{h.C.R}unknown lab id(s):{h.C.X} {', '.join(sorted(unknown))}")
            sys.exit(2)
        labs = [lab for lab in labs if lab.id in wanted]
    if args.skip:
        skip = {x.strip() for x in args.skip.split(",") if x.strip()}
        labs = [lab for lab in labs if lab.id not in skip]
    if getattr(args, "from_lab", None):
        if args.from_lab not in manifest.LABS_BY_ID:
            h.say(f"{h.C.R}unknown lab id:{h.C.X} {args.from_lab}")
            sys.exit(2)
        start = manifest.LABS_BY_ID[args.from_lab].order
        labs = [lab for lab in labs if lab.order >= start]
    return labs


def render_markdown(ctx: h.Ctx, pf: h.Preflight, results: list[LabResult], started: str) -> str:
    lines = [
        "# Live lab validation",
        "",
        f"- Workspace: `{ctx.host}`",
        f"- Project: `{ctx.project_id}`",
        f"- Started: {started}",
        "",
        "## Project configuration",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in pf.facts.items()]
    if pf.warnings:
        lines += ["", "## Configuration warnings", ""] + [f"- {w}" for w in pf.warnings]
    lines += ["", "## Results", "", "| Lab | Status | Time | Detail |", "| --- | --- | --- | --- |"]
    for r in results:
        detail = r.reason or ("skipped" if r.status == SKIP else "ok")
        lines.append(f"| `{r.id}` | {r.status} | {h.fmt_duration(r.duration_s)} | {detail} |")
    problems = [r for r in results if r.status == FAIL]
    if problems:
        lines += ["", "## Failures", ""]
        for r in problems:
            lines += [f"### `{r.id}` — {r.reason}", "", f"- Path: `{r.path}`"]
            if r.run_page_url:
                lines.append(f"- Run: {r.run_page_url}")
            if r.failed_cell:
                lines.append(f"- Failed at {r.failed_cell}")
            if r.error:
                lines.append(f"- Error: `{r.error.splitlines()[0][:300]}`")
            for cell in r.skipped_cells[:5]:
                lines.append(f"- Never ran: `{cell}`")
            if len(r.skipped_cells) > 5:
                lines.append(f"- ...and {len(r.skipped_cells) - 5} more cell(s)")
            for s in r.missing_sentinels:
                lines.append(f"- Missing sentinel: `{s}`")
            for s in r.forbidden_hits:
                lines.append(f"- Swallowed failure printed: `{s}`")
            for c in r.checks:
                if not c.ok:
                    lines.append(f"- Post-condition failed ({c.kind}): {c.label} — {c.detail}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the workshop labs live and assert they worked.")
    ap.add_argument("--profile", help="Databricks CLI profile (defaults to .workshop-config PROFILE)")
    ap.add_argument("--target", default="dev", help="bundle target (default: dev)")
    ap.add_argument("--only", help="comma-separated lab ids to run")
    ap.add_argument("--skip", help="comma-separated lab ids to skip")
    ap.add_argument("--from", dest="from_lab", help="start at this lab id and continue in order")
    ap.add_argument("--no-deploy", action="store_true", help="skip `databricks bundle deploy`")
    ap.add_argument("--preflight-only", action="store_true", help="report configuration and exit")
    ap.add_argument("--dry-run", action="store_true", help="print the plan without running anything")
    ap.add_argument("--ignore-gates", action="store_true", help="run gated labs even if unavailable")
    ap.add_argument("--data-api-url", default="", help="Data API base URL for the data-api lab")
    ap.add_argument("--sp-app-id", default="", help="service principal app id for the data-api lab")
    args = ap.parse_args()

    h.require_sdk()
    problems = manifest.validate_manifest()
    if problems:
        h.say(f"{h.C.R}manifest is invalid:{h.C.X}")
        for p in problems:
            h.say(f"  - {p}")
        return 2

    ctx = h.build_ctx(profile=args.profile, target=args.target)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    h.say(f"{h.C.B}Live lab validation{h.C.X}  {h.C.DIM}{ctx.host}{h.C.X}")
    h.say(f"{h.C.DIM}project {ctx.project_id} | schema {ctx.pg_schema} | profile {ctx.profile}{h.C.X}\n")

    h.say(f"{h.C.B}▶ Preflight{h.C.X}")
    pf = h.run_preflight(ctx)
    for k, v in pf.facts.items():
        h.say(f"  {h.C.DIM}{k:26}{h.C.X} {v}")
    for gate, ok in sorted(pf.gates.items()):
        mark = f"{h.C.G}✓{h.C.X}" if ok else f"{h.C.Y}—{h.C.X}"
        h.say(f"  {mark} gate {gate}: {'available' if ok else 'unavailable'}")
    for w in pf.warnings:
        h.say(f"  {h.C.Y}⚠{h.C.X} {w}")
    if pf.failures:
        for f in pf.failures:
            h.say(f"  {h.C.R}✗{h.C.X} {f}")
        return 1
    if args.preflight_only:
        return 0

    labs = select_labs(args)
    if args.dry_run:
        h.say(f"\n{h.C.B}▶ Plan{h.C.X}")
        for lab in labs:
            gated = [g for g in lab.gates if not pf.gates.get(g, False)]
            note = ""
            if lab.deferred:
                note = f"{h.C.Y}skip (deferred){h.C.X}"
            elif gated and not args.ignore_gates:
                note = f"{h.C.Y}skip (gate: {', '.join(gated)}){h.C.X}"
            h.say(f"  {lab.order:>4} {lab.id:<16} {lab.path}  {note}")
        return 0

    file_path = ""
    if not args.no_deploy:
        h.say(f"\n{h.C.B}▶ Deploying bundle{h.C.X}")
        h.bundle_deploy(ctx)
        h.say(f"  {h.C.G}✓{h.C.X} bundle deployed to target {ctx.bundle_target}")
    file_path = h.bundle_file_path(ctx)
    h.say(f"  {h.C.DIM}notebook root: {file_path}{h.C.X}")

    extra_params = {}
    if args.data_api_url:
        extra_params["rest_endpoint"] = args.data_api_url
    if args.sp_app_id:
        extra_params["sp_app_id"] = args.sp_app_id
    elif pf.facts.get("app_sp"):
        extra_params["sp_app_id"] = pf.facts["app_sp"]

    h.say(f"\n{h.C.B}▶ Running {len(labs)} lab(s){h.C.X}")
    results: list[LabResult] = []
    for lab in labs:
        if lab.deferred and not args.ignore_gates:
            h.say(f"  {h.C.Y}—{h.C.X} {lab.id:<16} skipped (deferred: {lab.deferred})")
            results.append(LabResult(id=lab.id, path=lab.path, status=SKIP,
                                     reason=f"deferred: {lab.deferred}"))
            continue
        gated = [g for g in lab.gates if not pf.gates.get(g, False)]
        if gated and not args.ignore_gates:
            h.say(f"  {h.C.Y}—{h.C.X} {lab.id:<16} skipped (gate unavailable: {', '.join(gated)})")
            results.append(LabResult(id=lab.id, path=lab.path, status=SKIP,
                                     reason=f"gate unavailable: {', '.join(gated)}"))
            continue
        h.say(f"  {h.C.DIM}▸{h.C.X} {lab.id:<16} {h.C.DIM}{lab.path}{h.C.X}")
        params = extra_params if lab.id == "data_api" else {}
        res = run_lab(ctx, lab, file_path, params)
        results.append(res)
        mark = f"{h.C.G}✓{h.C.X}" if res.status == PASS else f"{h.C.R}✗{h.C.X}"
        h.say(f"    {mark} {res.status} in {h.fmt_duration(res.duration_s)}"
              + (f"{h.C.Y} (after one retry){h.C.X}" if res.retried else "")
              + (f" — {res.reason}" if res.reason else ""))
        for c in res.checks:
            if not c.ok:
                h.say(f"      {h.C.R}✗{h.C.X} {c.label}: {c.detail}")
        for s in res.missing_sentinels:
            h.say(f"      {h.C.R}✗{h.C.X} missing sentinel: {s!r}")
        for s in res.forbidden_hits:
            h.say(f"      {h.C.R}✗{h.C.X} swallowed failure printed: {s!r}")
        for cell in res.skipped_cells[:3]:
            h.say(f"      {h.C.R}✗{h.C.X} never ran: {cell}")
        if res.status == FAIL and res.error:
            h.say(f"      {h.C.DIM}{res.error.splitlines()[0][:200]}{h.C.X}")

    passed = [r for r in results if r.status == PASS]
    failed = [r for r in results if r.status == FAIL]
    skipped = [r for r in results if r.status == SKIP]

    payload = {
        "started": started,
        "workspace": ctx.host,
        "project": ctx.project_id,
        "profile": ctx.profile,
        "preflight": {"gates": pf.gates, "facts": pf.facts, "warnings": pf.warnings},
        "summary": {"passed": len(passed), "failed": len(failed), "skipped": len(skipped)},
        "results": h.dataclass_list(results),
    }
    report = h.write_report("live-labs", payload,
                            markdown=render_markdown(ctx, pf, results, started))

    h.say(f"\n{h.C.B}── Summary ─────────────────────────────{h.C.X}")
    h.say(f"  passed  : {len(passed)}")
    h.say(f"  failed  : {len(failed)}")
    h.say(f"  skipped : {len(skipped)}")
    h.say(f"  report  : {report.relative_to(h.REPO)}")
    for r in failed:
        h.say(f"  {h.C.R}✗{h.C.X} {r.id}: {r.reason}")
    for r in skipped:
        h.say(f"  {h.C.Y}—{h.C.X} {r.id}: {r.reason}")
    if failed:
        h.say(f"\n{h.C.R}LIVE VALIDATION FAILED{h.C.X}")
        return 1
    h.say(f"\n{h.C.G}LIVE VALIDATION PASSED{h.C.X}"
          + (f" {h.C.Y}({len(skipped)} skipped){h.C.X}" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
