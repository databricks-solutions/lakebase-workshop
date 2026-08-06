"""Declarative inventory of every runnable workshop artifact.

This module is the single source of truth for the live validation harness
(`run_labs_live.py`, `reset_lab_state.py`, `validate_all.py`) and for the static
checks in `validate_workshop.py`. It is deliberately stdlib-only so CI can import
it without installing the Databricks SDK.

Placeholders usable in `sql`, `creates`, and `params` values:
    {schema}     participant Postgres schema  (lakebase_lab_<user>)
    {catalog}    Unity Catalog catalog        (main)
    {uc_schema}  Unity Catalog schema         (lakebase_lab_<user>)
    {project}    Lakebase project id          (lakebase-lab-<user>)
    {user}       participant email
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Feature gates. A lab declaring a gate is skipped (not failed) when preflight
# reports the gate unavailable, because these are workspace/UI-level opt-ins
# that a participant may legitimately not have turned on.
# --------------------------------------------------------------------------- #
GATE_APP = "app"            # Lab Console app deployed in the workspace
GATE_SEARCH = "search"      # Lakebase Search enabled on the project (UI, irreversible)
GATE_DATA_API = "data_api"  # Data API enabled on the project -> `authenticator` role
GATE_SPARK = "spark"        # notebook needs Spark / UC write access


@dataclass(frozen=True)
class Check:
    """A post-condition asserted after the lab run finishes.

    kind="sql":  `spec` is a query returning exactly one scalar; compared against
                 `expect` (e.g. ">= 5", "== 0"). Runs on `branch`.
    kind="sdk":  `spec` names a handler in run_labs_live.SDK_CHECKS, optionally
                 with a ":argument" suffix.
    """

    label: str
    kind: str
    spec: str
    expect: str = ">= 1"
    branch: str = "production"


def sql(label: str, spec: str, expect: str = ">= 1", branch: str = "production") -> Check:
    return Check(label=label, kind="sql", spec=spec, expect=expect, branch=branch)


def sdk(label: str, spec: str) -> Check:
    return Check(label=label, kind="sdk", spec=spec)


@dataclass(frozen=True)
class Lab:
    """One runnable artifact.

    sentinels   substrings that MUST appear in captured stdout
    forbidden   substrings that must NOT appear — these are the messages labs print
                from `except` blocks that would otherwise let a broken lab report
                success, so they are treated as failures rather than warnings
    creates     teardown handles consumed by reset_lab_state.py, in the order they
                must be removed (children before parents)
    """

    id: str
    path: str
    order: int
    kind: str = "notebook"  # "notebook" | "sql"
    timeout_s: int = 900
    requires: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    params: dict[str, str] = field(default_factory=dict)
    sentinels: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    checks: tuple[Check, ...] = ()
    creates: tuple[str, ...] = ()
    notes: str = ""
    # Set to explain why a lab is knowingly incomplete. It is skipped rather than
    # failed, so an unfinished lab cannot masquerade as a passing one.
    deferred: str = ""


# Printed by labs/_setup.py when the seeded schema had to be repaired. On a
# correctly set-up project this never fires, so treat it as a failure everywhere.
REPAIR_WARNING = "⚠ Missing tables in"

# Every table the seed creates; asserted after setup.
SEEDED_TABLES = (
    "products",
    "events",
    "agent_sessions",
    "agent_messages",
    "agent_memory_store",
    "audit_log",
)


LABS: tuple[Lab, ...] = (
    # ------------------------------------------------------------------ #
    Lab(
        id="setup",
        path="notebooks/00_Setup_Lakebase_Project.py",
        order=10,
        timeout_s=1800,
        sentinels=(
            "✓ Connected to Lakebase",
            "created and seeded",
            "✓ Granted CAN_MANAGE on project",
            "✓ databricks_auth extension ready",
            "✓ Granted SP access to schema:",
            "WORKSHOP CONFIGURATION",
        ),
        # The app lookup is wrapped in a try/except that only warns, which would
        # silently skip every SP grant and break the Lab Console pages later.
        forbidden=("⚠ Could not look up app", REPAIR_WARNING),
        checks=(
            sdk("Lakebase project exists", "project_exists"),
            sdk("production endpoint is past provisioning", "endpoint_ready:production"),
            sdk("app SP holds CAN_MANAGE on the project", "project_acl_has_app_sp"),
            sql(
                "all 6 seeded tables exist",
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = '{schema}' AND table_name IN "
                "('products','events','agent_sessions','agent_messages','agent_memory_store','audit_log')",
                "== 6",
            ),
            sql("products seeded", "SELECT count(*) FROM {schema}.products", ">= 8"),
        ),
        notes="Foundation. Creates the project, seeds the schema, and grants the app SP "
        "both the project ACL (layer 1) and Postgres privileges (layer 2).",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="auth",
        path="labs/authentication/Authentication_and_Permissions.py",
        order=20,
        timeout_s=900,
        requires=("setup",),
        sentinels=("✓ Connected", "Current user:", "Your connection details:", "SSL in use:"),
        forbidden=(REPAIR_WARNING,),
        notes="Read-only. Good cheap smoke test that OAuth token minting and TLS work.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="app_deploy",
        path="labs/app-deployment/Deploy_Lab_Console_App.py",
        order=30,
        timeout_s=900,
        requires=("setup",),
        gates=(GATE_APP,),
        sentinels=(
            "✓ Granted CAN_MANAGE on project",
            "✓ databricks_auth extension ready",
            "✓ Granted SP access to schema:",
            "✓ The Lab Console app can now access your Lakebase project.",
        ),
        checks=(sdk("app SP holds CAN_MANAGE on the project", "project_acl_has_app_sp"),),
        notes="Does not deploy the app (the facilitator does that via the bundle); it "
        "replays the two-layer SP grants. Calls w.apps.get without a guard, so it "
        "hard-fails when the app is absent.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="observability",
        path="labs/observability/Observability_and_Monitoring.py",
        order=40,
        timeout_s=900,
        requires=("setup",),
        sentinels=("✓ Connected to", "✓ pg_stat_statements extension enabled", "Database Overview"),
        forbidden=("pg_stat_statements not available:", REPAIR_WARNING),
        checks=(
            sql(
                "pg_stat_statements installed",
                "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'",
                "== 1",
            ),
        ),
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="data_ops",
        path="labs/data-operations/Data_Operations.py",
        order=50,
        timeout_s=900,
        requires=("setup",),
        sentinels=(
            "✓ Metadata updated",
            "✓ Inserted:",
            "✓ Updated:",
            "✓ Deleted:",
            "✓ Transaction committed",
        ),
        forbidden=(REPAIR_WARNING,),
        checks=(
            sql(
                "CRUD demo row cleaned up by the lab itself",
                "SELECT count(*) FROM {schema}.products WHERE name = 'Workshop Notebook'",
                "== 0",
            ),
            sql(
                "Electronics rows carry the sale metadata",
                "SELECT count(*) FROM {schema}.products "
                "WHERE category = 'Electronics' AND metadata ? 'on_sale'",
                ">= 1",
            ),
            sql(
                "transaction demo committed both rows",
                "SELECT count(*) FROM {schema}.events "
                "WHERE event_type = 'transaction_demo' AND source = 'notebook-03'",
                ">= 2",
            ),
        ),
        creates=("rows:events:source=notebook-03",),
        notes="Adds 2 events rows and ~8 audit_log rows per run; reset trims them so "
        "row-count assertions stay exact across repeat runs.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="advanced_sql",
        path="labs/data-operations/Advanced_Postgres.sql",
        order=60,
        kind="sql",
        timeout_s=600,
        requires=("setup",),
        checks=(
            sql(
                "window/CTE demo tagged product 1",
                "SELECT count(*) FROM {schema}.products "
                "WHERE product_id = 1 AND 'workshop-tested' = ANY(tags)",
                "== 1",
            ),
            sql(
                "advanced-sql transaction committed",
                "SELECT count(*) FROM {schema}.events "
                "WHERE event_type = 'transaction_demo' AND source = 'advanced-sql'",
                ">= 2",
            ),
        ),
        creates=(
            "rows:events:source=advanced-sql",
            "tag:products:product_id=1:workshop-tested",
        ),
        notes="Plain .sql file, not a notebook. Executed statement-by-statement over "
        "psycopg with search_path set to the participant schema. Appends "
        "'workshop-tested' to product 1's tags on every run, so reset must strip it.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="agent_memory",
        path="labs/agentic-memory/Agent_Memory.py",
        order=70,
        timeout_s=900,
        requires=("setup",),
        sentinels=(
            "✓ Thread created:",
            "✓ Stored 7 messages in thread",
            "✓ Stored 5 long-term memories for",
        ),
        forbidden=(REPAIR_WARNING,),
        checks=(
            sql(
                "long-term memories upserted (5 topics, not duplicated)",
                "SELECT count(*) FROM {schema}.agent_memory_store WHERE user_id = '{user}'",
                "== 5",
            ),
            sql(
                "conversation thread persisted with all 7 messages",
                "SELECT count(*) FROM {schema}.agent_messages m JOIN {schema}.agent_sessions s "
                "ON s.session_id = m.session_id "
                "WHERE s.metadata->>'purpose' = 'lakebase-workshop-demo'",
                ">= 7",
            ),
        ),
        creates=("rows:agent_sessions:metadata->>'purpose'=lakebase-workshop-demo",),
        notes="Uses a fresh uuid thread per run, so sessions/messages accumulate; the "
        "memory store is a real upsert and stays at 5 rows.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="search",
        path="labs/lakebase-search/Lakebase_Search.py",
        order=80,
        timeout_s=900,
        requires=("setup",),
        gates=(GATE_SEARCH,),
        sentinels=(
            "✓ Connected to production branch",
            "installed — Search is ready",
            "✓ search_documents built: 5 rows",
        ),
        # Without these the notebook prints a diagnosis and runs every later cell as
        # a no-op, finishing green while exercising none of Lakebase Search.
        forbidden=(
            "✗ Could not install the Lakebase Search extensions.",
            "Skipped — enable Lakebase Search first",
            REPAIR_WARNING,
        ),
        checks=(
            sql(
                "lakebase_vector + lakebase_text installed",
                "SELECT count(*) FROM pg_extension WHERE extname IN ('lakebase_vector','lakebase_text')",
                "== 2",
            ),
            sql("search corpus built", "SELECT count(*) FROM {schema}.search_documents", "== 5"),
        ),
        creates=("pg_table:search_documents",),
        notes="Requires Lakebase Search enabled on the project (UI, irreversible). "
        "Drops and rebuilds its own table, so it is naturally repeatable.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="branches",
        path="labs/development-experience/Branches_and_Environments.py",
        order=90,
        timeout_s=1800,
        requires=("setup",),
        sentinels=(
            "✓ Connected to dev branch",
            "✓ Reviews table created and seeded on dev branch",
            "✓ Branch isolation confirmed",
        ),
        forbidden=(REPAIR_WARNING,),
        checks=(
            sdk("dev branch exists", "branch_exists:lab-dev-01"),
            sql(
                "reviews table seeded on the dev branch",
                "SELECT count(*) FROM {schema}.reviews",
                ">= 3",
                branch="lab-dev-01",
            ),
            sql(
                "production stayed clean (branch isolation)",
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = '{schema}' AND table_name = 'reviews'",
                "== 0",
            ),
        ),
        creates=("branch:lab-dev-01",),
        notes="Creates a 24h-TTL child of production. The isolation proof depends on "
        "production NOT having a reviews table, so reset must delete the branch.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="autoscale",
        path="labs/development-experience/Autoscaling_and_Compute.py",
        order=100,
        timeout_s=900,
        requires=("setup",),
        sentinels=("Min CU:", "Max CU:", "RAM range:"),
        notes="Inspection-only as shipped; the resize is commented out. Teaches nothing "
        "observable when the endpoint is pinned to a fixed size, which preflight flags.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="ha",
        path="labs/development-experience/High_Availability_and_Replicas.py",
        order=110,
        timeout_s=900,
        requires=("setup",),
        sentinels=("Endpoints on production:",),
        forbidden=(REPAIR_WARNING,),
        notes="Inspection-only; HA is enabled through the UI.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="backup",
        path="labs/backup-recovery/Backup_and_Recovery.py",
        order=120,
        timeout_s=3000,
        requires=("setup",),
        sentinels=(
            "✓ Connected to work branch",
            "💥 Products table dropped!",
            "✓ Products on recovered branch:",
            "Data is fully intact",
        ),
        forbidden=(REPAIR_WARNING,),
        checks=(
            sdk("snapshot branch exists", "branch_exists:lab-snapshot-pre-migration"),
            sdk("recovery branch exists", "branch_exists:lab-recovered"),
            sql(
                "recovered branch still has the products data",
                "SELECT count(*) FROM {schema}.products",
                ">= 8",
                branch="lab-recovered",
            ),
            sql(
                "production products untouched by the simulated bad migration",
                "SELECT count(*) FROM {schema}.products",
                ">= 8",
            ),
        ),
        # Deletion order matters: lab-recovered is a child of the snapshot branch and
        # a branch with children cannot be deleted.
        creates=(
            "branch:lab-migration-test",
            "branch:lab-recovered",
            "branch:lab-snapshot-pre-migration",
        ),
        notes="Longest of the branch labs (three branch creates plus endpoint waits). "
        "The snapshot branch is created with no_expiry=True, so it survives forever "
        "unless reset removes it — the main source of drift between runs.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="reverse_etl",
        path="labs/reverse-etl/Reverse_ETL.py",
        order=130,
        timeout_s=3600,
        requires=("setup",),
        gates=(GATE_SPARK, GATE_APP),
        sentinels=(
            "✓ Sample data created in",
            "Synced table",
            "✓ New rows upserted into sample table.",
            "✓ Granted UC access to the Lab Console SP",
        ),
        forbidden=("not deployed yet — skip this step now", REPAIR_WARNING),
        checks=(
            sdk("synced table reached a healthy state", "synced_table_ready:products_synced"),
            sdk("managed sync pipeline last update succeeded", "synced_table_pipeline_ok:products_synced"),
            sql(
                "synced rows landed in Postgres",
                "SELECT count(*) FROM {schema}.products_synced",
                ">= 5",
            ),
            sdk("app SP can read the UC schema", "uc_grant_app_sp:{catalog}.{uc_schema}"),
        ),
        creates=(
            "synced_table:{catalog}.{uc_schema}.products_synced",
            "uc_table:{catalog}.{uc_schema}.sample_products",
        ),
        notes="Spark + UC + synced table provisioning; one of the two long poles.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="feature_store",
        path="labs/online-feature-store/Online_Feature_Store.py",
        order=140,
        timeout_s=4200,
        requires=("setup",),
        gates=(GATE_SPARK,),
        sentinels=(
            "✓ Feature Engineering client initialized",
            "✓ Change Data Feed enabled on",
            "✓ Online store ready",
            "✓ Feature table published to online store",
            "✓ Merged 2 customers into",
            "✓ Re-published with updated features",
        ),
        forbidden=(
            "Could not connect to Lakebase project:",
            "⚠ Online table in error state",
            REPAIR_WARNING,
        ),
        checks=(
            sdk("online table is healthy", "online_table_ok:customer_features_online"),
            sdk(
                "feature table has the merged rows",
                "uc_row_count:{catalog}.{uc_schema}.customer_features:>=12",
            ),
        ),
        creates=(
            "online_table:{catalog}.{uc_schema}.customer_features_online",
            "uc_table:{catalog}.{uc_schema}.customer_features",
        ),
        notes="Publishes twice (initial + after a merge); the other long pole. Skips "
        "feature-table creation when the table already exists, so reset must drop it "
        "to exercise the create path.",
    ),
    # ------------------------------------------------------------------ #
    Lab(
        id="data_api",
        path="labs/data-api/Data_API.py",
        order=150,
        timeout_s=900,
        requires=("setup",),
        gates=(GATE_DATA_API,),
        params={"enable_data_api": "no", "rest_endpoint": "", "sp_app_id": ""},
        sentinels=(
            "✓ Connected to production branch",
            "Policies on api_clients",
            "✓ Role created and granted for SP",
            "Same request via the Lab Console service principal -> 200",
        ),
        # A skip message means the section never ran: a green job that validated
        # nothing. The direct owner call is expected to be rejected, so only the
        # proxied call has to succeed.
        forbidden=(
            "✗ Could not create/grant the API role.",
            "No Data API URL",
            "Set the `sp_app_id` widget",
            "Data API is not enabled on this project.",
            REPAIR_WARNING,
        ),
        checks=(
            sql("api_clients seeded", "SELECT count(*) FROM {schema}.api_clients", "== 3"),
            sql(
                "row-level security policy in place",
                "SELECT count(*) FROM pg_policy WHERE polname = 'api_clients_owner'",
                "== 1",
            ),
        ),
        creates=("pg_table:api_clients",),
        notes="Requires the Data API enabled on the project, which creates the "
        "`authenticator` role. The lab can enable it itself via the enable_data_api "
        "widget. HTTP calls cannot be made from the notebook at all: the Data API "
        "rejects the project owner, and the Apps gateway rejects a job's ephemeral "
        "token, so the successful call is only exercised by validate_app.py.",
        deferred="section 4 (HTTP calls) is being reworked — a notebook job cannot "
        "authenticate to either the Data API (owner) or the Lab Console app "
        "(Apps gateway rejects job tokens)",
    ),
)


LABS_BY_ID = {lab.id: lab for lab in LABS}
RUN_ORDER = tuple(sorted(LABS, key=lambda lab: lab.order))


def resolve(text: str, ctx: dict[str, str]) -> str:
    """Substitute {schema}/{catalog}/{uc_schema}/{project}/{user} placeholders."""
    return text.format(**ctx)


def validate_manifest() -> list[str]:
    """Self-check the manifest. Returns a list of problems (empty when healthy)."""
    problems: list[str] = []
    seen_orders: dict[int, str] = {}
    for lab in LABS:
        if lab.kind not in ("notebook", "sql"):
            problems.append(f"{lab.id}: unknown kind {lab.kind!r}")
        if lab.order in seen_orders:
            problems.append(f"{lab.id}: duplicate order {lab.order} (shared with {seen_orders[lab.order]})")
        seen_orders[lab.order] = lab.id
        for dep in lab.requires:
            if dep not in LABS_BY_ID:
                problems.append(f"{lab.id}: requires unknown lab {dep!r}")
            elif LABS_BY_ID[dep].order >= lab.order:
                problems.append(f"{lab.id}: requires {dep!r} which does not run earlier")
        for check in lab.checks:
            if check.kind not in ("sql", "sdk"):
                problems.append(f"{lab.id}: check {check.label!r} has unknown kind {check.kind!r}")
        overlap = set(lab.sentinels) & set(lab.forbidden)
        if overlap:
            problems.append(f"{lab.id}: {sorted(overlap)} listed as both sentinel and forbidden")
    return problems
