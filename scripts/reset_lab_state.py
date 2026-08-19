#!/usr/bin/env python3
"""Tear down everything the labs create so the next run starts from a clean slate.

Repeatability is the point. Several labs are only idempotent in the weak sense that
they do not crash on a second run: the backup lab's checkpoint branch never expires,
the branches lab's dev branch keeps production's isolation proof from being
meaningful, and the data/agent labs append rows that row-count assertions depend on.
This script removes exactly those artifacts.

Safety: teardown is driven by lab_manifest `creates` entries and an explicit
allowlist. The participant's project, its `production` branch, the primary endpoint,
and the seeded tables are never touched.

Usage:
  python scripts/reset_lab_state.py --dry-run    # show what would be removed
  python scripts/reset_lab_state.py              # remove it
  python scripts/reset_lab_state.py --keep-branches
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import harness_common as h
import lab_manifest as manifest

# Nothing outside this set is ever deleted, however the manifest changes.
BRANCH_ALLOWLIST = {
    "lab-dev-01",
    "lab-migration-test",
    "lab-recovered",
    "lab-checkpoint-pre-migration",
    # Former name of the checkpoint branch; kept so a project that ran an older
    # version of the backup lab still gets cleaned up.
    "lab-snapshot-pre-migration",
    "pitr-recovery",
}
PROTECTED_BRANCHES = {"production"}

# Tables the seed owns; a lab-created table may be dropped, these may not.
SEEDED_TABLES = set(manifest.SEEDED_TABLES)


@dataclass
class Action:
    kind: str
    target: str
    status: str = "pending"
    detail: str = ""


@dataclass
class ResetReport:
    actions: list[Action] = field(default_factory=list)

    def add(self, kind: str, target: str) -> Action:
        action = Action(kind=kind, target=target)
        self.actions.append(action)
        return action


def planned_actions(ctx: h.Ctx) -> list[tuple[str, str]]:
    """Ordered (kind, target) pairs derived from the manifest.

    Manifest order matters for branches: a branch with children cannot be deleted,
    and lab-recovered is a child of lab-checkpoint-pre-migration.
    """
    ph = ctx.placeholders()
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for lab in manifest.RUN_ORDER:
        for entry in lab.creates:
            resolved = manifest.resolve(entry, ph)
            kind, _, target = resolved.partition(":")
            pair = (kind, target)
            if pair not in seen:
                seen.add(pair)
                ordered.append(pair)
    # Non-branch cleanup first: dropping a synced table also removes its pipeline,
    # and rows must go before the tables they live in are considered.
    return sorted(ordered, key=lambda p: p[0] == "branch")


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def drop_branch(ctx: h.Ctx, name: str, action: Action, dry_run: bool) -> None:
    if name in PROTECTED_BRANCHES or name not in BRANCH_ALLOWLIST:
        action.status = "refused"
        action.detail = "not in the lab branch allowlist"
        return
    try:
        ctx.w.postgres.get_branch(name=ctx.branch_name(name))
    except Exception:
        action.status = "absent"
        return
    if dry_run:
        action.status = "would-delete"
        return
    try:
        ctx.w.postgres.delete_branch(name=ctx.branch_name(name)).wait()
        action.status = "deleted"
    except Exception as e:
        action.status = "error"
        action.detail = f"{type(e).__name__}: {str(e)[:200]}"


def drop_synced_table(ctx: h.Ctx, full_name: str, action: Action, dry_run: bool) -> None:
    resource = f"synced_tables/{full_name}"
    try:
        ctx.w.postgres.get_synced_table(name=resource)
    except Exception:
        action.status = "absent"
        return
    if dry_run:
        action.status = "would-delete"
        return
    try:
        ctx.w.postgres.delete_synced_table(name=resource)
        action.status = "deleted"
    except Exception as e:
        action.status = "error"
        action.detail = f"{type(e).__name__}: {str(e)[:200]}"


def drop_online_table(ctx: h.Ctx, full_name: str, action: Action, dry_run: bool) -> None:
    """Delete a published online table.

    Publishing into a Lakebase project produces a synced table, and the Online
    Tables API refuses those, so existence has to be read from the synced-table
    API. Deletion still prefers the Feature Engineering call, which is the
    teardown the lab teaches.
    """
    try:
        ctx.w.postgres.get_synced_table(name=f"synced_tables/{full_name}")
    except Exception:
        action.status = "absent"
        return
    if dry_run:
        action.status = "would-delete"
        return
    errors = []
    for label, delete in (
        ("feature_store.delete_online_table",
         lambda: ctx.w.feature_store.delete_online_table(online_table_name=full_name)),
        ("postgres.delete_synced_table",
         lambda: ctx.w.postgres.delete_synced_table(name=f"synced_tables/{full_name}")),
    ):
        try:
            delete()
            action.status = "deleted"
            return
        except Exception as e:
            msg = str(e)
            if "does not exist" in msg.lower() or "not found" in msg.lower():
                action.status = "absent"
                return
            errors.append(f"{label}: {type(e).__name__}: {msg[:120]}")
    action.status = "error"
    action.detail = " | ".join(errors)


def drop_online_destination(ctx: h.Ctx, full_name: str, action: Action, dry_run: bool) -> None:
    """Drop the Postgres table an online table published into.

    Publishing writes to a database named after the Unity Catalog catalog rather
    than `databricks_postgres`, and a publish that fails partway leaves the
    destination table behind. Every later publish then refuses the name, so this
    table has to go for a run to be repeatable.
    """
    catalog, schema, table = full_name.split(".")
    try:
        conn = h.pg_connect(ctx, "production", dbname=catalog)
    except Exception as e:
        action.status = "skipped"
        action.detail = f"cannot reach database {catalog}: {type(e).__name__}"
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM pg_tables WHERE schemaname = %s AND tablename = %s",
                (schema, table),
            )
            if not cur.fetchone()["n"]:
                action.status = "absent"
                return
            if dry_run:
                action.status = "would-drop"
                return
            cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
        conn.commit()
        action.status = "dropped"
    except Exception as e:
        action.status = "error"
        action.detail = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        conn.close()


def drop_uc_table(ctx: h.Ctx, full_name: str, action: Action, dry_run: bool) -> None:
    try:
        ctx.w.tables.get(full_name=full_name)
    except Exception:
        action.status = "absent"
        return
    if dry_run:
        action.status = "would-drop"
        return
    try:
        ctx.w.tables.delete(full_name=full_name)
        action.status = "dropped"
    except Exception as e:
        action.status = "error"
        action.detail = f"{type(e).__name__}: {str(e)[:200]}"


def drop_postgres_catalog(ctx: h.Ctx, catalog_id: str, action: Action, dry_run: bool) -> None:
    """Unregister a Lakebase→UC federated catalog (labs/unity-catalog-access).

    Deletes the Unity Catalog entry only — the Postgres database is untouched.
    """
    resource = catalog_id if catalog_id.startswith("catalogs/") else f"catalogs/{catalog_id}"
    try:
        ctx.w.postgres.get_catalog(name=resource)
    except Exception:
        action.status = "absent"
        return
    if dry_run:
        action.status = "would-delete"
        return
    try:
        ctx.w.postgres.delete_catalog(name=resource).wait()
        action.status = "deleted"
    except Exception as e:
        action.status = "error"
        action.detail = f"{type(e).__name__}: {str(e)[:200]}"


def drop_pg_table(conn, schema: str, table: str, action: Action, dry_run: bool) -> None:
    if table in SEEDED_TABLES:
        action.status = "refused"
        action.detail = "seeded table, not lab-created"
        return
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, table),
        )
        if not cur.fetchone()["n"]:
            action.status = "absent"
            return
    if dry_run:
        action.status = "would-drop"
        return
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
    conn.commit()
    action.status = "dropped"


def delete_rows(conn, schema: str, spec: str, action: Action, dry_run: bool) -> None:
    """spec: '<table>:<column>=<value>' or '<table>:<json path>=<value>'."""
    table, _, predicate = spec.partition(":")
    column, _, value = predicate.partition("=")
    where = f"{column} = %s"
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{table}" WHERE {where}', (value,))
        count = cur.fetchone()["n"]
    if not count:
        action.status = "absent"
        return
    action.detail = f"{count} row(s)"
    if dry_run:
        action.status = "would-delete"
        return
    with conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{schema}"."{table}" WHERE {where}', (value,))
    conn.commit()
    action.status = "deleted"


def strip_tag(conn, schema: str, spec: str, action: Action, dry_run: bool) -> None:
    """spec: '<table>:<pk column>=<pk value>:<tag>' — remove every copy of a tag."""
    table, _, rest = spec.partition(":")
    predicate, _, tag = rest.partition(":")
    column, _, value = predicate.partition("=")
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT count(*) AS n FROM "{schema}"."{table}" '
            f"WHERE {column} = %s AND %s = ANY(tags)",
            (value, tag),
        )
        if not cur.fetchone()["n"]:
            action.status = "absent"
            return
    if dry_run:
        action.status = "would-strip"
        return
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{schema}"."{table}" SET tags = array_remove(tags, %s) WHERE {column} = %s',
            (tag, value),
        )
    conn.commit()
    action.status = "stripped"


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Remove all lab-created state for a repeatable run.")
    ap.add_argument("--profile", help="Databricks CLI profile")
    ap.add_argument("--dry-run", action="store_true", help="report without deleting")
    ap.add_argument("--keep-branches", action="store_true", help="leave lab branches in place")
    ap.add_argument("--keep-uc", action="store_true", help="leave UC tables and synced/online tables")
    args = ap.parse_args()

    h.require_sdk()
    ctx = h.build_ctx(profile=args.profile)
    mode = "dry run" if args.dry_run else "live"
    h.say(f"{h.C.B}Reset lab state{h.C.X} {h.C.DIM}({mode}){h.C.X}")
    h.say(f"{h.C.DIM}project {ctx.project_id} | schema {ctx.pg_schema}{h.C.X}\n")

    report = ResetReport()
    actions = planned_actions(ctx)
    needs_pg = any(kind in ("pg_table", "rows", "tag") for kind, _ in actions)

    conn = None
    if needs_pg:
        try:
            conn = h.pg_connect(ctx)
        except Exception as e:
            h.say(f"{h.C.Y}⚠{h.C.X} cannot reach Postgres, skipping in-database cleanup: {e}")

    for kind, target in actions:
        if kind == "branch" and args.keep_branches:
            continue
        if kind in ("uc_table", "synced_table", "online_table", "postgres_catalog") and args.keep_uc:
            continue
        action = report.add(kind, target)
        if kind == "branch":
            drop_branch(ctx, target, action, args.dry_run)
        elif kind == "synced_table":
            drop_synced_table(ctx, target, action, args.dry_run)
        elif kind == "online_table":
            drop_online_table(ctx, target, action, args.dry_run)
            drop_online_destination(
                ctx, target, report.add("online_destination", target), args.dry_run
            )
        elif kind == "uc_table":
            drop_uc_table(ctx, target, action, args.dry_run)
        elif kind == "postgres_catalog":
            drop_postgres_catalog(ctx, target, action, args.dry_run)
        elif conn is None:
            action.status = "skipped"
            action.detail = "no Postgres connection"
        elif kind == "pg_table":
            drop_pg_table(conn, ctx.pg_schema, target, action, args.dry_run)
        elif kind == "rows":
            delete_rows(conn, ctx.pg_schema, target, action, args.dry_run)
        elif kind == "tag":
            strip_tag(conn, ctx.pg_schema, target, action, args.dry_run)
        else:
            action.status = "skipped"
            action.detail = f"no handler for kind {kind!r}"

    if conn is not None:
        conn.close()

    colour = {
        "deleted": h.C.G, "dropped": h.C.G, "stripped": h.C.G,
        "absent": h.C.DIM, "skipped": h.C.Y, "refused": h.C.Y, "error": h.C.R,
    }
    for action in report.actions:
        mark = colour.get(action.status, h.C.DIM)
        suffix = f" — {action.detail}" if action.detail else ""
        h.say(f"  {mark}{action.status:>13}{h.C.X}  {action.kind}:{action.target}{suffix}")

    errors = [a for a in report.actions if a.status == "error"]
    changed = [a for a in report.actions if a.status in ("deleted", "dropped", "stripped")]
    h.say(f"\n{h.C.B}── Summary ─────────────────────────────{h.C.X}")
    h.say(f"  actions : {len(report.actions)}")
    h.say(f"  changed : {len(changed)}")
    h.say(f"  errors  : {len(errors)}")
    h.write_report("reset", {
        "project": ctx.project_id,
        "dry_run": args.dry_run,
        "actions": h.dataclass_list(report.actions),
    })
    if errors:
        h.say(f"\n{h.C.R}RESET INCOMPLETE{h.C.X}")
        return 1
    h.say(f"\n{h.C.G}RESET COMPLETE{h.C.X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
