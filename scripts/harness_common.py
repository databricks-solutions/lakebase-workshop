#!/usr/bin/env python3
"""Shared plumbing for the live workshop validation harness.

Used by run_labs_live.py, reset_lab_state.py, validate_app.py, and validate_all.py.
Unlike validate_workshop.py (offline, stdlib-only) this module needs the Databricks
SDK and psycopg, and it talks to a real workspace.

The participant-derived names here mirror labs/_setup.py exactly. If that file's
_sanitize() changes, change sanitize() below with it or the harness will validate a
different project than the labs create.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO / ".validation-reports"

# Let sibling harness modules import each other regardless of the caller's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_manifest as manifest  # noqa: E402


class C:
    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[34m"; DIM = "\033[2m"; X = "\033[0m"


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# Participant naming — must match labs/_setup.py
# --------------------------------------------------------------------------- #
def sanitize(email: str) -> str:
    name = email.split("@")[0]
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", name.lower())).strip("-")


def project_id_for(email: str) -> str:
    return f"lakebase-lab-{sanitize(email)}"


def pg_schema_for(email: str) -> str:
    return f"lakebase_lab_{sanitize(email).replace('-', '_')}"


# --------------------------------------------------------------------------- #
# Config / context
# --------------------------------------------------------------------------- #
def load_workshop_config() -> dict[str, str]:
    """Parse .workshop-config (KEY=VALUE). Tolerates stray non-KEY=VALUE lines."""
    cfg: dict[str, str] = {}
    path = REPO / ".workshop-config"
    if not path.is_file():
        return cfg
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if re.fullmatch(r"[A-Z0-9_]+", key):
            cfg[key] = value.strip()
    return cfg


@dataclass
class Ctx:
    w: object  # WorkspaceClient
    profile: str
    user_email: str
    project_id: str
    pg_schema: str
    uc_catalog: str
    uc_schema: str
    app_name: str
    host: str
    bundle_target: str

    def placeholders(self) -> dict[str, str]:
        return {
            "schema": self.pg_schema,
            "catalog": self.uc_catalog,
            "uc_schema": self.uc_schema,
            # Federated Lakebase→UC catalog from labs/unity-catalog-access
            "fed_catalog": f"lb_fed_{sanitize(self.user_email).replace('-', '_')}",
            "project": self.project_id,
            "user": self.user_email,
        }

    def project_name(self) -> str:
        return f"projects/{self.project_id}"

    def branch_name(self, branch: str) -> str:
        return f"projects/{self.project_id}/branches/{branch}"


def build_ctx(profile: str | None = None, target: str = "dev", uc_catalog: str = "main") -> Ctx:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config

    cfg = load_workshop_config()
    profile = profile or cfg.get("PROFILE") or "DEFAULT"
    # A sweep makes hundreds of API calls; one that never returns would stall the
    # whole run with no output, so cap every request rather than trusting defaults.
    w = WorkspaceClient(config=Config(profile=profile, http_timeout_seconds=120))
    try:
        email = w.current_user.me().user_name
    except Exception as e:
        if is_network_flap(e):
            raise RuntimeError(
                "this machine's IP is blocked by the workspace IP ACL — connect to the "
                "VPN and try again"
            ) from e
        raise
    return Ctx(
        w=w,
        profile=profile,
        user_email=email,
        project_id=cfg.get("PROJECT_ID") or project_id_for(email),
        pg_schema=pg_schema_for(email),
        uc_catalog=uc_catalog,
        uc_schema=pg_schema_for(email),
        app_name=cfg.get("APP_NAME") or "lakebase-lab-console",
        host=(w.config.host or "").rstrip("/"),
        bundle_target=target,
    )


# --------------------------------------------------------------------------- #
# Postgres
# --------------------------------------------------------------------------- #
def endpoint_for(ctx: Ctx, branch: str):
    """First endpoint of a branch, or None when the branch has no compute."""
    endpoints = list(ctx.w.postgres.list_endpoints(parent=ctx.branch_name(branch)))
    if not endpoints:
        return None
    return ctx.w.postgres.get_endpoint(name=endpoints[0].name)


def is_network_flap(e: Exception) -> bool:
    """A VPN drop shows up as the workspace rejecting the new source IP."""
    msg = str(e)
    return "blocked by Databricks IP ACL" in msg or "Source IP address" in msg


def ride_out_network_flap(call, tries: int = 20, wait_s: int = 30):
    """Retry a workspace call while the caller's IP is blocked.

    A sweep runs for half an hour, so a VPN reconnect part way through should cost
    a pause rather than the whole run.
    """
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return call()
        except Exception as e:
            if not is_network_flap(e):
                raise
            last = e
            if attempt == 1:
                say(f"{C.Y}⚠{C.X} this machine's IP is blocked by the workspace IP ACL "
                    f"(VPN down?) — waiting up to {tries * wait_s // 60} min for it to return")
            time.sleep(wait_s)
    raise last  # type: ignore[misc]


def pg_connect(ctx: Ctx, branch: str = "production", retries: int = 4,
               dbname: str = "databricks_postgres"):
    """Connect to a branch as the participant.

    Deliberately does NOT repair the schema the way labs/_setup.get_connection does:
    the harness must observe the state the labs left behind, not fix it.

    Labs work in `databricks_postgres`, but published online tables land in a
    separate database named after the Unity Catalog catalog, so teardown has to be
    able to reach that one too.
    """
    import psycopg
    from psycopg.rows import dict_row

    endpoints = list(ctx.w.postgres.list_endpoints(parent=ctx.branch_name(branch)))
    if not endpoints:
        raise RuntimeError(f"branch {branch!r} has no endpoint")
    ep = ctx.w.postgres.get_endpoint(name=endpoints[0].name)
    cred = ctx.w.postgres.generate_database_credential(endpoint=endpoints[0].name)
    params = {
        "host": ep.status.hosts.host,
        "dbname": dbname,
        "user": ctx.user_email,
        "password": cred.token,
        "sslmode": "require",
        "options": f"-c search_path={ctx.pg_schema},public",
    }
    last: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            return psycopg.connect(**params, row_factory=dict_row, connect_timeout=30)
        except psycopg.OperationalError as e:  # scale-to-zero wake / transient network
            last = e
            time.sleep(4)
    raise last  # type: ignore[misc]


def scalar(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    if row is None:
        return None
    return next(iter(row.values()))


EXPECT_RX = re.compile(r"^\s*(==|!=|>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def evaluate_expect(value, expect: str) -> tuple[bool, str]:
    """Compare a scalar against an expectation like '>= 5'."""
    m = EXPECT_RX.match(expect)
    if not m:
        return False, f"unparsable expectation {expect!r}"
    op, raw = m.group(1), m.group(2)
    want = float(raw)
    try:
        got = float(value)
    except (TypeError, ValueError):
        return False, f"non-numeric result {value!r}"
    ok = {
        "==": got == want, "!=": got != want, ">=": got >= want,
        "<=": got <= want, ">": got > want, "<": got < want,
    }[op]
    return ok, f"got {value!r}, expected {expect.strip()}"


# --------------------------------------------------------------------------- #
# Bundle
# --------------------------------------------------------------------------- #
def cli(*args: str, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["databricks", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"`databricks {' '.join(args)}` failed ({proc.returncode})\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    return proc


def bundle_file_path(ctx: Ctx) -> str:
    """Workspace root the bundle syncs repo files into."""
    proc = cli("bundle", "validate", "-t", ctx.bundle_target, "-p", ctx.profile, "-o", "json")
    return json.loads(proc.stdout)["workspace"]["file_path"].rstrip("/")


def bundle_deploy(ctx: Ctx) -> None:
    cli("bundle", "deploy", "-t", ctx.bundle_target, "-p", ctx.profile, timeout=1800)


def workspace_notebook_path(file_path: str, repo_relative: str) -> str:
    """Map a repo path to its synced workspace notebook path (extension stripped)."""
    return f"{file_path}/{repo_relative[:-3] if repo_relative.endswith('.py') else repo_relative}"


# --------------------------------------------------------------------------- #
# Notebook job execution + output capture
#
# get_run_output() only returns dbutils.notebook.exit() payloads, and the labs
# communicate through print(). export_run() embeds the executed notebook — cell
# sources AND their stdout — as a URL-encoded JSON blob inside the exported HTML,
# so that is what we parse to assert on sentinels.
# --------------------------------------------------------------------------- #
MODEL_RX = re.compile(r"__DATABRICKS_NOTEBOOK_MODEL\s*=\s*'([^']+)'")
TERMINAL_LIFECYCLE = ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")


@dataclass
class Cell:
    position: float
    state: str
    source: str
    stdout: str
    executed: bool

    @property
    def is_magic(self) -> bool:
        """A cell whose first line is a magic (%md, %run, %sql, %pip, ...).

        The exported notebook model reports executed=False for these even when they
        ran — a lab that clearly used %run ../_setup still shows it as unexecuted —
        so they cannot be used to detect an early abort.
        """
        first = next((line for line in self.source.splitlines() if line.strip()), "")
        return first.lstrip().removeprefix("# MAGIC").lstrip().startswith("%")

    @property
    def first_line(self) -> str:
        return next((line for line in self.source.splitlines() if line.strip()), "(empty cell)")


@dataclass
class RunOutcome:
    run_id: int | None = None
    task_run_id: int | None = None
    result_state: str = ""
    life_cycle_state: str = ""
    state_message: str = ""
    run_page_url: str = ""
    duration_s: float = 0.0
    error: str = ""
    cells: list[Cell] = field(default_factory=list)
    timed_out: bool = False

    @property
    def stdout(self) -> str:
        return "\n".join(c.stdout for c in self.cells if c.stdout)

    @property
    def failed_cell(self) -> Cell | None:
        return next((c for c in self.cells if c.state == "error" and c.executed), None)

    @property
    def unexecuted(self) -> int:
        return sum(1 for c in self.cells if not c.executed)

    @property
    def skipped_code_cells(self) -> list[Cell]:
        """Code cells that never ran, i.e. everything after an abort.

        Magic and blank cells always report executed=False, so only real code counts.
        A run can report SUCCESS with a long tail of these when the kernel dies
        mid-notebook, which is the difference between "the lab passed" and "the lab
        stopped early".
        """
        return [
            c for c in self.cells
            if not c.executed and not c.is_magic and c.source.strip()
        ]

    @property
    def kernel_died(self) -> bool:
        return "kernel is unresponsive" in f"{self.error} {self.state_message}".lower()

    @property
    def succeeded(self) -> bool:
        return self.result_state == "SUCCESS"


def parse_run_cells(ctx: Ctx, task_run_id: int) -> list[Cell]:
    from databricks.sdk.service.jobs import ViewsToExport

    export = ctx.w.jobs.export_run(run_id=task_run_id, views_to_export=ViewsToExport.CODE)
    cells: list[Cell] = []
    for view in export.views or []:
        match = MODEL_RX.search(view.content or "")
        if not match:
            continue
        raw = urllib.parse.unquote(base64.b64decode(match.group(1)).decode())
        model = json.loads(raw)
        for cmd in sorted(model.get("commands") or [], key=lambda c: c.get("position") or 0):
            results = cmd.get("results") or {}
            chunks: list[str] = []
            data = results.get("data")
            if isinstance(data, list):
                chunks = [d.get("data") or "" for d in data
                          if isinstance(d, dict) and d.get("type") == "ansi"]
            elif isinstance(data, str):
                chunks = [data]
            cells.append(Cell(
                position=float(cmd.get("position") or 0),
                state=str(cmd.get("state") or ""),
                source=(cmd.get("command") or "").strip(),
                stdout=strip_ansi("".join(chunks)),
                # Cells after a failure are reported as "error" with no results at
                # all; that means never executed, not failed.
                executed=bool(results),
            ))
    return cells


ANSI_RX = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_RX.sub("", text)


def run_notebook(
    ctx: Ctx,
    notebook_path: str,
    *,
    run_name: str,
    params: dict[str, str] | None = None,
    timeout_s: int = 900,
    poll_s: int = 15,
) -> RunOutcome:
    """Run a notebook as a serverless job, then capture per-cell stdout."""
    from databricks.sdk.service.jobs import NotebookTask, SubmitTask

    out = RunOutcome()
    started = time.time()
    submitted = ctx.w.jobs.submit(
        run_name=run_name,
        tasks=[SubmitTask(
            task_key="lab",
            # No cluster spec -> serverless compute, which is what participants use.
            notebook_task=NotebookTask(notebook_path=notebook_path, base_parameters=params or {}),
        )],
    )
    out.run_id = submitted.run_id

    run = None
    while True:
        run = ride_out_network_flap(lambda: ctx.w.jobs.get_run(run_id=out.run_id))
        state = run.state
        life = str(getattr(state, "life_cycle_state", "") or "")
        if state.result_state is not None or any(t in life for t in TERMINAL_LIFECYCLE):
            break
        if time.time() - started > timeout_s:
            out.timed_out = True
            try:
                ctx.w.jobs.cancel_run(run_id=out.run_id)
            except Exception:
                pass
            break
        time.sleep(poll_s)

    out.duration_s = round(time.time() - started, 1)
    out.life_cycle_state = str(getattr(run.state, "life_cycle_state", "") or "").split(".")[-1]
    out.result_state = str(getattr(run.state, "result_state", "") or "").split(".")[-1]
    out.state_message = run.state.state_message or ""
    out.run_page_url = run.run_page_url or ""

    task_run_id = run.tasks[0].run_id if run.tasks else out.run_id
    out.task_run_id = task_run_id
    try:
        detail = ctx.w.jobs.get_run_output(run_id=task_run_id)
        out.error = (detail.error or "").strip()
    except Exception as e:
        out.error = out.error or f"(could not read run output: {e})"
    try:
        out.cells = parse_run_cells(ctx, task_run_id)
        # The exported notebook model lags the run's terminal state by a moment, so a
        # cell that finished can briefly export with no results and look skipped. Only
        # a second look confirms an early abort.
        if out.succeeded and out.skipped_code_cells:
            time.sleep(15)
            out.cells = parse_run_cells(ctx, task_run_id)
    except Exception as e:
        out.error = f"{out.error}\n(could not parse notebook output: {e})".strip()
    return out


# --------------------------------------------------------------------------- #
# Preflight
#
# Feature gates decide whether a lab runs at all; facts and warnings tell the
# facilitator when the project is configured such that a lab runs green but
# demonstrates the wrong thing (a fixed-size endpoint has no autoscaling to
# observe, a 1-day history window contradicts the documented 2-30 day range).
# --------------------------------------------------------------------------- #
@dataclass
class Preflight:
    gates: dict[str, bool] = field(default_factory=dict)
    facts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _duration_seconds(value) -> float | None:
    """Seconds from a protobuf Duration, a '3600s' string, or a number."""
    if value is None:
        return None
    seconds = getattr(value, "seconds", None)
    if seconds is not None:
        return float(seconds) + float(getattr(value, "nanos", 0) or 0) / 1e9
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)s?", str(value).strip())
    return float(m.group(1)) if m else None


def run_preflight(ctx: Ctx) -> Preflight:
    """Inspect the workspace and project, returning gates + configuration facts."""
    pf = Preflight()
    pf.facts["workspace"] = ctx.host
    pf.facts["user"] = ctx.user_email
    pf.facts["project"] = ctx.project_id

    # --- project ---------------------------------------------------------- #
    project = None
    try:
        project = ctx.w.postgres.get_project(name=ctx.project_name())
    except Exception as e:
        pf.facts["project_state"] = f"absent ({type(e).__name__})"
        pf.warnings.append(
            f"project {ctx.project_id} does not exist yet — the setup lab will create it, "
            "so the first run will be slower"
        )
    if project is not None:
        status = project.status
        pf.facts["project_state"] = "exists"
        pf.facts["pg_version"] = str(getattr(status, "pg_version", "?"))
        pf.facts["owner"] = str(getattr(status, "owner", "?"))
        retention = _duration_seconds(getattr(status, "history_retention_duration", None))
        if retention is not None:
            days = retention / 86400
            pf.facts["history_retention"] = f"{days:g} day(s)"
            if days < 2:
                pf.warnings.append(
                    f"history retention is {days:g} day(s); the backup lab documents a 2-30 day "
                    "range with a 7-day default, so its PITR narrative does not match this project"
                )
        defaults = getattr(status, "default_endpoint_settings", None)
        if defaults is not None:
            pf.facts["default_endpoint_cu"] = (
                f"{getattr(defaults, 'autoscaling_limit_min_cu', '?')}"
                f"-{getattr(defaults, 'autoscaling_limit_max_cu', '?')} CU"
            )
            suspend = _duration_seconds(getattr(defaults, "suspend_timeout_duration", None))
            if suspend is not None:
                pf.facts["default_suspend_timeout"] = f"{suspend:g}s"

    # --- production endpoint ---------------------------------------------- #
    try:
        ep = endpoint_for(ctx, "production")
    except Exception as e:
        ep = None
        pf.warnings.append(f"could not read the production endpoint: {e}")
    if ep is not None:
        st = ep.status
        state = str(getattr(st, "current_state", ""))
        min_cu = getattr(st, "autoscaling_limit_min_cu", None)
        max_cu = getattr(st, "autoscaling_limit_max_cu", None)
        pf.facts["production_endpoint"] = f"{state} ({min_cu}-{max_cu} CU)"
        if min_cu is not None and max_cu is not None and min_cu == max_cu:
            pf.warnings.append(
                f"production endpoint is fixed at {min_cu} CU; the autoscaling lab will print a "
                "single value and demonstrate no scaling range"
            )
        group = getattr(st, "group", None)
        if group is not None:
            pf.facts["ha_group"] = (
                f"min={getattr(group, 'min', '?')} max={getattr(group, 'max', '?')} "
                f"readable_secondaries={getattr(group, 'enable_readable_secondaries', '?')}"
            )
            if not getattr(group, "enable_readable_secondaries", False):
                pf.warnings.append(
                    "readable secondaries are disabled, so the HA lab will only ever list one "
                    "endpoint and cannot show a replica"
                )

    # --- branches (root-branch quota is 3) -------------------------------- #
    try:
        branches = [b.name.rsplit("/", 1)[-1] for b in ctx.w.postgres.list_branches(parent=ctx.project_name())]
        pf.facts["branches"] = ", ".join(sorted(branches)) or "(none)"
        leftovers = [b for b in branches if b.startswith("lab-") or b == "pitr-recovery"]
        if leftovers:
            pf.warnings.append(
                f"lab branches left over from a previous run: {', '.join(sorted(leftovers))} — "
                "run reset_lab_state.py for a clean, repeatable run"
            )
    except Exception as e:
        pf.warnings.append(f"could not list branches: {e}")

    # --- Lab Console app --------------------------------------------------- #
    try:
        app = ctx.w.apps.get(name=ctx.app_name)
        sp = getattr(app, "effective_service_principal_client_id", None) or app.service_principal_client_id
        pf.gates[manifest.GATE_APP] = True
        pf.facts["app"] = f"{ctx.app_name} ({getattr(app.compute_status, 'state', '?')})"
        pf.facts["app_sp"] = str(sp)
    except Exception as e:
        pf.gates[manifest.GATE_APP] = False
        pf.facts["app"] = f"absent ({type(e).__name__})"
        pf.warnings.append(
            f"app {ctx.app_name!r} is not deployed; the app-deployment lab hard-fails without it "
            "and Reverse ETL cannot grant it UC access"
        )

    # --- Unity Catalog ----------------------------------------------------- #
    try:
        ctx.w.catalogs.get(name=ctx.uc_catalog)
        pf.gates[manifest.GATE_SPARK] = True
    except Exception as e:
        pf.gates[manifest.GATE_SPARK] = False
        pf.warnings.append(f"catalog {ctx.uc_catalog!r} is not reachable ({e}); Spark labs will fail")

    # --- Postgres-side gates ---------------------------------------------- #
    if project is not None:
        try:
            conn = pg_connect(ctx)
            try:
                # Availability is not enablement: both extensions ship in the catalogue
                # on every project, but CREATE EXTENSION fails with "must be loaded via
                # shared_preload_libraries" until Lakebase Search is switched on, which
                # is what actually adds them to the preload list.
                preload = scalar(conn, "SHOW shared_preload_libraries") or ""
                preloaded = [
                    ext for ext in ("lakebase_vector", "lakebase_text") if ext in str(preload)
                ]
                pf.facts["search_preloaded"] = ", ".join(preloaded) or "(none)"
                pf.gates[manifest.GATE_SEARCH] = len(preloaded) == 2
                if not pf.gates[manifest.GATE_SEARCH]:
                    pf.warnings.append(
                        "Lakebase Search is not enabled on this project (lakebase_vector / "
                        "lakebase_text are not in shared_preload_libraries); the search lab "
                        "will be skipped"
                    )
                authenticator = scalar(
                    conn, "SELECT count(*) FROM pg_roles WHERE rolname = 'authenticator'"
                )
                pf.gates[manifest.GATE_DATA_API] = int(authenticator or 0) == 1
                if not pf.gates[manifest.GATE_DATA_API]:
                    pf.warnings.append(
                        "the Data API is not enabled on this project (no `authenticator` role); "
                        "the data-api lab will be skipped"
                    )
            finally:
                conn.close()
        except Exception as e:
            pf.gates.setdefault(manifest.GATE_SEARCH, False)
            pf.gates.setdefault(manifest.GATE_DATA_API, False)
            pf.warnings.append(f"could not connect to Postgres for gate detection: {e}")
    else:
        pf.gates.setdefault(manifest.GATE_SEARCH, False)
        pf.gates.setdefault(manifest.GATE_DATA_API, False)

    return pf


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
SECRET_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9._\-]{20,}"), "<redacted-jwt>"),
    (re.compile(r"\bdapi[a-f0-9]{16,}\b"), "<redacted-pat>"),
    (re.compile(r"(?i)(password\s*[=:]\s*)\S+"), r"\1<redacted>"),
    (re.compile(r"(?i)(token[\"']?\s*[=:]\s*[\"']?)[A-Za-z0-9._\-]{16,}"), r"\1<redacted>"),
    (re.compile(r"(?i)(Token preview:\s*)\S+"), r"\1<redacted>"),
]


def scrub(text: str) -> str:
    """Redact credentials before anything is written to a report on disk."""
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def scrub_obj(obj):
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_obj(v) for v in obj]
    return obj


def write_report(name: str, payload: dict, *, markdown: str | None = None) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = scrub_obj(payload)
    json_path = REPORT_DIR / f"{name}-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    latest = REPORT_DIR / f"{name}-latest.json"
    latest.write_text(json.dumps(payload, indent=2, default=str))
    if markdown:
        (REPORT_DIR / f"{name}-{stamp}.md").write_text(scrub(markdown))
        (REPORT_DIR / f"{name}-latest.md").write_text(scrub(markdown))
    return json_path


def dataclass_list(items) -> list[dict]:
    return [asdict(i) for i in items]


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def require_sdk() -> None:
    try:
        import databricks.sdk  # noqa: F401
        import psycopg  # noqa: F401
    except ImportError as e:
        say(f"{C.R}Missing dependency:{C.X} {e}")
        say('Install with: pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6"')
        sys.exit(2)
