#!/usr/bin/env python3
"""Exercise the Lab Console API against the state the labs left behind.

The second half of the workshop promise is that every lab also works in the app.
A page that renders but shows an empty table is a failure a screenshot would miss,
so each check here asserts on the payload, not just the status code.

Requests carry the caller's OAuth token; the Databricks Apps proxy injects the
X-Forwarded-Email header the backend routes on, so this exercises the same
per-user routing a participant gets in the browser. Note that the app's own
service principal performs the database work, which is exactly why it must hold
the grants the setup and Reverse ETL labs give it.

Usage:
  python scripts/validate_app.py                    # all checks
  python scripts/validate_app.py --after setup,data_ops
  python scripts/validate_app.py --list
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import harness_common as h
import lab_manifest as manifest

Assertion = Callable[[Any], "tuple[bool, str]"]


@dataclass
class ApiCheck:
    label: str
    path: str
    method: str = "GET"
    body: dict | None = None
    expect_status: int = 200
    assertion: Assertion | None = None
    # Lab whose run this check depends on; used by --after to select a subset.
    after: str = "setup"


@dataclass
class ApiResult:
    label: str
    path: str
    method: str
    status: str = "pass"
    http_status: int = 0
    detail: str = ""
    duration_s: float = 0.0


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #
def non_empty_list(payload: Any) -> tuple[bool, str]:
    if not isinstance(payload, list):
        return False, f"expected a list, got {type(payload).__name__}"
    return bool(payload), f"{len(payload)} item(s)"


def has_keys(*keys: str) -> Assertion:
    def check(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, f"expected an object, got {type(payload).__name__}"
        missing = [k for k in keys if not payload.get(k)]
        return (not missing), (f"missing/empty: {missing}" if missing else f"has {list(keys)}")
    return check


def stat_at_least(field_name: str, minimum: int) -> Assertion:
    def check(payload: Any) -> tuple[bool, str]:
        value = (payload or {}).get(field_name)
        if not isinstance(value, (int, float)):
            return False, f"{field_name} missing or non-numeric ({value!r})"
        return value >= minimum, f"{field_name}={value} (need >= {minimum})"
    return check


def list_contains(predicate: Callable[[dict], bool], description: str) -> Assertion:
    def check(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, list):
            return False, f"expected a list, got {type(payload).__name__}"
        hit = any(isinstance(item, dict) and predicate(item) for item in payload)
        return hit, (f"found {description}" if hit else f"no item matching {description}")
    return check


def rows_returned(payload: Any) -> tuple[bool, str]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("rows")
    if not isinstance(rows, list):
        shape = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        return False, f"no rows in response ({shape})"
    return bool(rows), f"{len(rows)} row(s)"


def only_user_schema(schema: str) -> Assertion:
    """Non-empty, and nothing from Lakebase's internal schemas leaked in."""
    def check(payload: Any) -> tuple[bool, str]:
        if not isinstance(payload, list) or not payload:
            return False, "expected a non-empty list"
        foreign = sorted({
            row.get("schemaname") for row in payload
            if isinstance(row, dict) and row.get("schemaname") not in (schema, None)
        })
        return (not foreign), (f"{len(payload)} row(s), foreign schemas: {foreign}"
                               if foreign else f"{len(payload)} row(s), all in {schema}")
    return check


def search_ready(payload: Any) -> tuple[bool, str]:
    ready = (payload or {}).get("ready")
    table = (payload or {}).get("table_exists")
    return bool(ready and table), f"ready={ready} table_exists={table}"


def frontend_built(payload: Any) -> tuple[bool, str]:
    """The UI bundle is a gitignored build artifact, so it can be absent."""
    built = (payload or {}).get("frontend_built")
    return bool(built), (
        "UI bundle present" if built else
        "no frontend/dist in the deployment — run `npm run build` in "
        "apps/lakebase-lab-console/frontend, then redeploy"
    )


# --------------------------------------------------------------------------- #
# Checks, grouped by the lab that produces the state they assert on
# --------------------------------------------------------------------------- #
def build_checks(ctx: h.Ctx) -> list[ApiCheck]:
    return [
        # --- deployment integrity ------------------------------------------ #
        # Every other check below passes on a deployment that shipped no UI,
        # because the API is unaffected — participants are the ones who find out.
        ApiCheck("Deployment includes the built frontend", "/api/health",
                 assertion=frontend_built),
        # --- setup / data ------------------------------------------------- #
        ApiCheck("Dashboard table stats", "/api/data/stats",
                 assertion=stat_at_least("products", 8)),
        ApiCheck("Data playground lists products", "/api/data/products",
                 assertion=non_empty_list),
        ApiCheck("SQL playground runs a read-only query", "/api/data/query", "POST",
                 body={"sql": "SELECT count(*) AS n FROM products"}, assertion=rows_returned),
        # --- auth ---------------------------------------------------------- #
        # The route deliberately withholds the token itself and returns a preview plus
        # decoded JWT claims, so assert on those rather than on a raw credential.
        ApiCheck("Auth page mints a database credential", "/api/auth/credential",
                 assertion=has_keys("token_preview", "token_length", "jwt_claims"),
                 after="auth"),
        ApiCheck("Auth page reports connection info", "/api/auth/connection-info",
                 assertion=has_keys("host", "database", "username"), after="auth"),
        ApiCheck("Auth page lists Postgres roles", "/api/auth/roles",
                 assertion=non_empty_list, after="auth"),
        ApiCheck("Auth page reports TLS", "/api/auth/tls",
                 assertion=has_keys("ssl"), after="auth"),
        # --- observability ------------------------------------------------- #
        ApiCheck("Observability database overview", "/api/observability/database",
                 assertion=has_keys("datname", "cache_hit_ratio"), after="observability"),
        ApiCheck("Observability table stats are scoped to the participant's schema",
                 "/api/observability/tables",
                 assertion=only_user_schema(ctx.pg_schema), after="observability"),
        ApiCheck("Observability index stats are scoped to the participant's schema",
                 "/api/observability/indexes",
                 assertion=only_user_schema(ctx.pg_schema), after="observability"),
        ApiCheck("Observability relation sizes", "/api/observability/sizes",
                 assertion=non_empty_list, after="observability"),
        ApiCheck("Observability connections", "/api/observability/connections",
                 after="observability"),
        ApiCheck("Observability statements (pg_stat_statements)", "/api/observability/statements",
                 after="observability"),
        # --- data operations ----------------------------------------------- #
        ApiCheck("Events written by the data-ops lab are visible", "/api/data/events",
                 assertion=non_empty_list, after="data_ops"),
        ApiCheck("Audit trail is populated", "/api/data/audit",
                 assertion=non_empty_list, after="data_ops"),
        # --- agent memory --------------------------------------------------- #
        ApiCheck("Agent sessions from the memory lab", "/api/agent/sessions",
                 assertion=non_empty_list, after="agent_memory"),
        ApiCheck("Long-term memories from the memory lab", "/api/agent/memories",
                 assertion=non_empty_list, after="agent_memory"),
        ApiCheck("Memory store users", "/api/agent/memories/users",
                 assertion=non_empty_list, after="agent_memory"),
        # --- search --------------------------------------------------------- #
        ApiCheck("Search reports enabled with a built corpus", "/api/search/status",
                 assertion=search_ready, after="search"),
        ApiCheck("Hybrid search returns ranked results", "/api/search/query", "POST",
                 body={"mode": "hybrid", "query": "database search", "limit": 5},
                 assertion=rows_returned, after="search"),
        # --- branches / compute --------------------------------------------- #
        ApiCheck("Branch manager lists production", "/api/branches",
                 assertion=list_contains(lambda b: b.get("branch_id") == "production",
                                         "the production branch")),
        ApiCheck("Branch manager sees the lab dev branch", "/api/branches",
                 assertion=list_contains(lambda b: b.get("branch_id") == "lab-dev-01",
                                         "branch lab-dev-01"), after="branches"),
        ApiCheck("Compute page reads endpoint sizing", "/api/compute/production",
                 after="autoscale"),
        ApiCheck("Compute topology for production", "/api/compute/topology/production",
                 after="ha"),
        # --- backup --------------------------------------------------------- #
        ApiCheck("Backup page sees the checkpoint branch", "/api/branches",
                 assertion=list_contains(
                     lambda b: b.get("branch_id") == "lab-checkpoint-pre-migration",
                     "branch lab-checkpoint-pre-migration"), after="backup"),
        # --- reverse ETL / feature store -------------------------------------- #
        ApiCheck("Online stores include the participant project", "/api/online-tables/stores",
                 assertion=non_empty_list, after="reverse_etl"),
        ApiCheck("Synced Tables page lists the lab's synced table",
                 "/api/online-tables/synced-tables",
                 assertion=list_contains(lambda t: "products_synced" in str(t), "products_synced"),
                 after="reverse_etl"),
        ApiCheck("Feature Store page lists UC online tables",
                 "/api/online-tables/feature-specs",
                 assertion=non_empty_list, after="feature_store"),
        # --- data api -------------------------------------------------------- #
        # data_api_url is the endpoint every other Data API route resolves server-side,
        # so a null here silently breaks the whole page and its proxy.
        ApiCheck("Data API status resolves the project's endpoint", "/api/data-api/status",
                 assertion=has_keys("enabled", "data_api_url", "schema", "sp_app_id"),
                 after="data_api"),
    ]


# --------------------------------------------------------------------------- #
def app_base_url(ctx: h.Ctx) -> str:
    app = ctx.w.apps.get(name=ctx.app_name)
    state = str(getattr(app.compute_status, "state", ""))
    if "ACTIVE" not in state.upper():
        raise RuntimeError(f"app {ctx.app_name!r} is not running (state {state})")
    if not app.url:
        raise RuntimeError(f"app {ctx.app_name!r} has no URL")
    return app.url.rstrip("/")


def run_checks(ctx: h.Ctx, checks: list[ApiCheck]) -> list[ApiResult]:
    import requests

    base = app_base_url(ctx)
    token = ctx.w.config.oauth_token().access_token
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    results: list[ApiResult] = []

    # A check whose lab never ran because the feature is off says nothing about the
    # app, so it is skipped for the same reason the lab was.
    gated_off = ungated_labs(ctx)

    for check in checks:
        res = ApiResult(label=check.label, path=check.path, method=check.method)
        if check.after in gated_off:
            res.status = "skip"
            res.detail = f"lab {check.after} skipped: {gated_off[check.after]}"
            results.append(res)
            report_line(res)
            continue
        started = time.time()
        try:
            if check.method == "POST":
                response = session.post(base + check.path, json=check.body or {}, timeout=120)
            else:
                response = session.get(base + check.path, timeout=120)
            res.http_status = response.status_code
            res.duration_s = round(time.time() - started, 2)
            if response.status_code != check.expect_status:
                res.status = "fail"
                res.detail = f"HTTP {response.status_code}: {response.text[:200]}"
            elif check.assertion is not None:
                try:
                    payload = response.json()
                except ValueError:
                    res.status = "fail"
                    res.detail = "response was not JSON"
                else:
                    ok, detail = check.assertion(payload)
                    res.status = "pass" if ok else "fail"
                    res.detail = detail
        except Exception as e:
            res.status = "fail"
            res.duration_s = round(time.time() - started, 2)
            res.detail = f"{type(e).__name__}: {str(e)[:200]}"
        results.append(res)
        report_line(res)
    return results


def report_line(res: ApiResult) -> None:
    mark = {"pass": f"{h.C.G}✓{h.C.X}", "skip": f"{h.C.Y}—{h.C.X}"}.get(
        res.status, f"{h.C.R}✗{h.C.X}"
    )
    suffix = f" {h.C.DIM}{res.detail}{h.C.X}" if res.detail else ""
    h.say(f"  {mark} {res.method:<4} {res.path:<44} {res.label}{suffix}")


def ungated_labs(ctx: h.Ctx) -> dict[str, str]:
    """Lab ids that cannot run here, mapped to the reason, from preflight gates."""
    try:
        preflight = h.run_preflight(ctx)
    except Exception as e:
        h.say(f"{h.C.Y}⚠{h.C.X} preflight failed, running every check: {e}")
        return {}
    blocked: dict[str, str] = {}
    for lab in manifest.LABS:
        missing = [g for g in lab.gates if not preflight.gates.get(g, False)]
        if missing:
            blocked[lab.id] = f"gate unavailable: {', '.join(missing)}"
    return blocked


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the Lab Console API against post-lab state.")
    ap.add_argument("--profile", help="Databricks CLI profile")
    ap.add_argument("--after", help="only checks depending on these lab ids (comma-separated)")
    ap.add_argument("--list", action="store_true", help="list checks and exit")
    args = ap.parse_args()

    h.require_sdk()
    ctx = h.build_ctx(profile=args.profile)
    checks = build_checks(ctx)

    if args.after:
        wanted = {x.strip() for x in args.after.split(",") if x.strip()}
        checks = [c for c in checks if c.after in wanted]
    if args.list:
        for c in checks:
            h.say(f"  {c.after:<14} {c.method:<4} {c.path:<44} {c.label}")
        return 0

    h.say(f"{h.C.B}Lab Console API validation{h.C.X} {h.C.DIM}{ctx.app_name}{h.C.X}")
    h.say(f"{h.C.DIM}project {ctx.project_id} | as {ctx.user_email}{h.C.X}\n")
    results = run_checks(ctx, checks)

    failed = [r for r in results if r.status == "fail"]
    skipped = [r for r in results if r.status == "skip"]
    h.write_report("app-checks", {
        "app": ctx.app_name,
        "project": ctx.project_id,
        "summary": {
            "passed": len(results) - len(failed) - len(skipped),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "results": h.dataclass_list(results),
    })
    h.say(f"\n{h.C.B}── Summary ─────────────────────────────{h.C.X}")
    h.say(f"  checks  : {len(results)}")
    h.say(f"  failed  : {len(failed)}")
    h.say(f"  skipped : {len(skipped)}")
    for r in failed:
        h.say(f"  {h.C.R}✗{h.C.X} {r.method} {r.path} — {r.detail}")
    if failed:
        h.say(f"\n{h.C.R}APP VALIDATION FAILED{h.C.X}")
        return 1
    h.say(f"\n{h.C.G}APP VALIDATION PASSED{h.C.X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
