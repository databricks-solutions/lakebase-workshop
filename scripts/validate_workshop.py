#!/usr/bin/env python3
"""Validate the Lakebase Workshop notebooks, labs, and app before committing/deploying.

Fast, offline static checks by default (no workspace needed):
  - Databricks notebook syntax (compiles every Python cell)
  - Repo structure (each lab has a README + a runnable notebook; labs listed in
    labs/README.md actually exist)
  - Regression guard (stale facts we've fixed before must not reappear)
  - Markdown relative-link integrity
  - Backend Python compiles

Opt-in heavier checks:
  --frontend   Build the React app (npm run build) — needs node_modules
  --bundle     Run `databricks bundle validate` — needs a configured CLI profile
  --full       All of the above

Usage:
  python scripts/validate_workshop.py            # fast static checks
  python scripts/validate_workshop.py --full     # + frontend build + bundle validate

Exit code is 0 only when there are no failures (warnings do not fail the run).
"""
from __future__ import annotations

import argparse
import py_compile
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Directories we never scan.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".databricks", ".bundle", ".cursor", "agent-tools", ".egg-info",
    # Live-run reports quote the very code they flag, so scanning them would turn
    # every real finding into a permanent static failure.
    ".validation-reports",
}

# Files excluded from the regression grep (they legitimately quote old facts).
REGRESSION_EXCLUDE = {
    "scripts/validate_workshop.py",
}

# Stale facts that must not reappear in learner-facing content. (label, regex)
# Extend this list whenever an audit corrects a hard fact.
REGRESSIONS: list[tuple[str, str]] = [
    # Absolute max is 112 CU (fixed-size); autoscaling max remains 64 CU.
    ("do not claim autoscaling goes to 112 CU", r"(?i)autoscal(?:e|ing).{0,80}\b112\s*CU\b|\b112\s*CU\b.{0,80}autoscal(?:e|ing)"),
    ("autoscaling spread is <=16 CU (not 8)", r"spread[^.\n]{0,40}\b8\s*CU\b"),
    ("autoscaling range wording '0.5-32 CU' is stale", r"0\.5\s*[-\u2013]\s*32\s*CU"),
    ("restore window max is 30 days (not 35)", r"\b35[\s-]?day"),
    ("PITR SDK field is source_branch_time (not parent_timestamp)", r"parent_timestamp"),
    ("use 'Databricks Asset Bundle' (not 'Declarative Automation Bundle')", r"Declarative Automation Bundle"),
    ("project labs must link oltp/projects (not oltp/instances)", r"oltp/instances/"),
    ("lakehouse-sync is Public Preview / CDF (not 'Beta, UI-only')", r"Beta,\s*UI-only"),
    # The SDK interpolates securable_type into the URL path and the enum is not a
    # str subclass, so the member must be unwrapped with .value.
    ("pass SecurableType.<X>.value, not the enum member", r"SecurableType\.[A-Z_]+\b(?!\.value)"),
    # Requesting both in one pip install makes the resolver backtrack until the
    # environment is wedged and dbutils.library.restartPython() never returns.
    ("do not pin databricks-sdk alongside databricks-feature-engineering",
     r"pip install[^\n]*(?:databricks-sdk[^\n]*databricks-feature-engineering"
     r"|databricks-feature-engineering[^\n]*databricks-sdk)"),
    # It rewrites the schema, dropping the primary key and NOT NULL, which leaves a
    # feature table the online store will reject on every later publish.
    ("do not overwriteSchema on a table (drops primary keys)", r"overwriteSchema"),
]

# Lab folders allowed to ship without a runnable notebook (walkthrough-only).
README_ONLY_LABS = {"lakehouse-sync"}


class C:
    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; B = "\033[34m"; DIM = "\033[2m"; X = "\033[0m"


@dataclass
class Result:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def walk_files(*suffixes: str) -> list[Path]:
    out: list[Path] = []
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in p.parts):
            continue
        if suffixes and p.suffix not in suffixes:
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------- #
# 1. Notebook syntax
# --------------------------------------------------------------------------- #
def iter_python_cells(text: str):
    """Yield (cell_index, python_source) for Python cells in a Databricks notebook.

    Skips %md / %sql / other MAGIC cells and drops IPython magics (% / !) so the
    remaining lines are pure Python we can compile."""
    cells = re.split(r"^# COMMAND -+\s*$", text, flags=re.MULTILINE)
    for i, cell in enumerate(cells):
        lines = cell.splitlines()
        first = next((ln for ln in lines if ln.strip()), "")
        if first.strip().startswith("# MAGIC"):
            continue  # markdown / magic cell
        code_lines = []
        for ln in lines:
            s = ln.strip()
            if s == "# Databricks notebook source":
                continue
            if s.startswith("%") or s.startswith("!"):
                continue  # line magic / shell
            code_lines.append(ln)
        src = "\n".join(code_lines).strip()
        if src:
            yield i, src


def check_notebooks(res: Result) -> None:
    print(f"{C.B}▶ Notebook syntax{C.X}")
    notebooks = [p for p in walk_files(".py")
                 if rel(p).startswith(("labs/", "notebooks/"))]
    for nb in sorted(notebooks):
        res.checked += 1
        text = nb.read_text(encoding="utf-8")
        r = rel(nb)
        if not text.lstrip().startswith("# Databricks notebook source"):
            # _setup.py is a real notebook too; only warn if header missing.
            res.warn(f"{r}: missing '# Databricks notebook source' header")
        ok = True
        for idx, src in iter_python_cells(text):
            try:
                compile(src, f"{r}::cell{idx}", "exec")
            except SyntaxError as e:
                ok = False
                res.fail(f"{r}::cell{idx}: SyntaxError: {e.msg} (line {e.lineno})")
        # Lab notebooks should wire up the shared helpers.
        if r.startswith("labs/") and "%run ../_setup" not in text:
            res.warn(f"{r}: does not '%run ../_setup' (ok if intentional)")
        if ok:
            print(f"  {C.G}✓{C.X} {r}")
        else:
            print(f"  {C.R}✗{C.X} {r}")


# --------------------------------------------------------------------------- #
# 2. Structure
# --------------------------------------------------------------------------- #
def check_structure(res: Result) -> None:
    print(f"{C.B}▶ Lab structure{C.X}")
    labs_dir = REPO / "labs"
    for d in sorted(p for p in labs_dir.iterdir() if p.is_dir()):
        res.checked += 1
        name = d.name
        has_readme = (d / "README.md").is_file()
        notebooks = list(d.glob("*.py")) + list(d.glob("*.sql"))
        if not has_readme:
            res.fail(f"labs/{name}/ has no README.md")
        if not notebooks and name not in README_ONLY_LABS:
            res.fail(f"labs/{name}/ has no runnable notebook (.py/.sql)")
        marker = C.G + "✓" + C.X if (has_readme and (notebooks or name in README_ONLY_LABS)) else C.R + "✗" + C.X
        print(f"  {marker} labs/{name}/ (readme={has_readme}, notebooks={len(notebooks)})")

    # Labs referenced in labs/README.md must exist.
    readme = (labs_dir / "README.md").read_text(encoding="utf-8")
    for m in re.finditer(r"\|\s*\d+\s*\|\s*\[[^\]]+\]\(([a-z0-9-]+)/\)", readme):
        folder = m.group(1)
        if not (labs_dir / folder).is_dir():
            res.fail(f"labs/README.md references labs/{folder}/ which does not exist")


# --------------------------------------------------------------------------- #
# 3. Regression guard
# --------------------------------------------------------------------------- #
def check_regressions(res: Result) -> None:
    print(f"{C.B}▶ Regression guard (stale facts){C.X}")
    scan = [p for p in walk_files(".py", ".md", ".sql", ".jsx", ".js", ".sh")
            if rel(p) not in REGRESSION_EXCLUDE]
    hits = 0
    for label, pattern in REGRESSIONS:
        rx = re.compile(pattern)
        for p in scan:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits += 1
                    res.fail(f"{rel(p)}:{n}: {label} — found: {line.strip()[:100]}")
    if hits == 0:
        print(f"  {C.G}✓{C.X} no stale facts found ({len(REGRESSIONS)} patterns, {len(scan)} files)")
    else:
        print(f"  {C.R}✗{C.X} {hits} stale-fact hit(s)")


# --------------------------------------------------------------------------- #
# 3b. Postgres catalogue queries
#
# Two defects found by the live run, both invisible to a syntax check:
#   * pg_stat_user_indexes was queried for tablename / indexname, which only exist
#     on pg_tables and pg_indexes, so the statement failed at runtime.
#   * a query over the catalogue views was left unscoped, which pulls in Lakebase's
#     own __db_system and wal2delta objects — including a table named "tables" that
#     breaks any attempt to size it by bare name.
# --------------------------------------------------------------------------- #
# Only a FROM clause is a query; docstrings and prose mention these views by name.
STAT_VIEW_RX = re.compile(r"\bFROM\s+(pg_stat_user_(?:tables|indexes))\b", re.IGNORECASE)
COMMENT_RX = re.compile(r"--[^\n]*|^\s*#[^\n]*", re.MULTILINE)
WRONG_STAT_COLUMNS = ("tablename", "indexname")


def _statement_around(text: str, index: int) -> tuple[str, int]:
    """The SQL statement containing `index`, plus its starting line number.

    Bounded by a blank line, a semicolon, or a Python triple quote, which is enough
    to isolate one statement in both .sql files and inline notebook/backend SQL.
    """
    start = max(
        text.rfind("\n\n", 0, index),
        text.rfind(";", 0, index),
        text.rfind('"""', 0, index),
    )
    ends = [e for e in (text.find(";", index), text.find('"""', index)) if e != -1]
    end = min(ends) if ends else len(text)
    return text[start + 1:end], text.count("\n", 0, start + 1) + 1


def check_pg_catalog_queries(res: Result) -> None:
    print(f"{C.B}▶ Postgres catalogue queries{C.X}")
    problems = 0
    scanned = 0
    for p in sorted(walk_files(".py", ".sql")):
        if rel(p) in REGRESSION_EXCLUDE:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in STAT_VIEW_RX.finditer(text):
            scanned += 1
            stmt, line_no = _statement_around(text, m.start())
            # Comments explain these very column names, so they must not trip the check.
            lowered = COMMENT_RX.sub("", stmt).lower()
            view = m.group(1)
            if "schemaname" not in lowered:
                problems += 1
                res.fail(
                    f"{rel(p)}:{line_no}: {view} query is not scoped by schemaname, so it "
                    f"will include Lakebase's internal __db_system / wal2delta objects"
                )
            if view.endswith("indexes"):
                for column in WRONG_STAT_COLUMNS:
                    if re.search(rf"\b{column}\b", lowered):
                        problems += 1
                        res.fail(
                            f"{rel(p)}:{line_no}: {view} has no {column} column "
                            f"(use relname / indexrelname)"
                        )
    if problems == 0:
        print(f"  {C.G}✓{C.X} {scanned} catalogue query/queries scoped and using valid columns")
    else:
        print(f"  {C.R}✗{C.X} {problems} problem(s) in catalogue queries")


# --------------------------------------------------------------------------- #
# 4. Markdown relative links
# --------------------------------------------------------------------------- #
LINK_RX = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_links(res: Result) -> None:
    print(f"{C.B}▶ Markdown relative links{C.X}")
    broken = 0
    for md in sorted(walk_files(".md")):
        base = md.parent
        for n, line in enumerate(md.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for target in LINK_RX.findall(line):
                t = target.strip().split()[0]  # drop optional "title"
                t = t.split("#")[0]            # drop anchor
                if not t or t.startswith(("http://", "https://", "mailto:")):
                    continue
                cand = (base / t).resolve()
                if not cand.exists() and not (REPO / t).resolve().exists():
                    broken += 1
                    res.fail(f"{rel(md)}:{n}: broken relative link -> {t}")
    if broken == 0:
        print(f"  {C.G}✓{C.X} all relative links resolve")
    else:
        print(f"  {C.R}✗{C.X} {broken} broken link(s)")


# --------------------------------------------------------------------------- #
# 5. Backend python compiles
# --------------------------------------------------------------------------- #
def check_backend(res: Result) -> None:
    print(f"{C.B}▶ Backend Python compiles{C.X}")
    backend = REPO / "apps" / "lakebase-lab-console" / "backend"
    if not backend.is_dir():
        print(f"  {C.DIM}(no backend dir; skipped){C.X}")
        return
    files = [p for p in backend.rglob("*.py") if "__pycache__" not in p.parts]
    bad = 0
    for f in files:
        res.checked += 1
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            bad += 1
            res.fail(f"{rel(f)}: {e.msg.strip().splitlines()[-1] if e.msg else 'compile error'}")
    print(f"  {'%s✓%s' % (C.G, C.X) if bad == 0 else '%s✗%s' % (C.R, C.X)} {len(files)} backend file(s)")


# --------------------------------------------------------------------------- #
# 6. Secret / credential scan (offline, deterministic)
# --------------------------------------------------------------------------- #
# Files that legitimately contain secret-shaped patterns (this scanner, docs
# describing the patterns, and the secret-free example env).
SECRET_SCAN_EXCLUDE = {
    "scripts/validate_workshop.py",
    "apps/lakebase-lab-console/.env.example",
    "package-lock.json",
}

# (label, regex) — high-signal, low-false-positive credential patterns.
SECRET_PATTERNS: list[tuple[str, str]] = [
    ("Databricks PAT (dapi...)", r"\bdapi[0-9a-f]{20,}\b"),
    ("JWT literal (eyJ...)", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    ("AWS access key id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Private key block", r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    ("Hardcoded client secret", r"(?i)client_secret\s*[=:]\s*['\"][A-Za-z0-9._~+/-]{16,}['\"]"),
]

# Credential files that should never be committed.
CREDENTIAL_FILE_GLOBS = (
    "*.pem", "*.key", "credentials.json", "*service_account*.json",
    "*.tfstate", ".npmrc", ".pypirc",
)


def check_secrets(res: Result) -> None:
    print(f"{C.B}▶ Secret / credential scan{C.X}")
    scan = [
        p for p in walk_files(
            ".py", ".md", ".sql", ".jsx", ".js", ".ts", ".sh",
            ".yml", ".yaml", ".json", ".txt", ".cfg", ".ini", ".env",
        )
        if rel(p) not in SECRET_SCAN_EXCLUDE
    ]
    compiled = [(label, re.compile(rx)) for label, rx in SECRET_PATTERNS]
    hits = 0
    for p in scan:
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for label, rx in compiled:
                if rx.search(line):
                    hits += 1
                    res.fail(f"{rel(p)}:{n}: possible secret ({label})")

    # Credential files present in the tree.
    cred_files = 0
    for pattern in CREDENTIAL_FILE_GLOBS:
        for p in REPO.rglob(pattern):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            cred_files += 1
            res.fail(f"{rel(p)}: credential file should not be committed")

    if hits == 0 and cred_files == 0:
        print(f"  {C.G}✓{C.X} no secrets or credential files found ({len(scan)} files)")
    else:
        print(f"  {C.R}✗{C.X} {hits} secret hit(s), {cred_files} credential file(s)")


# --------------------------------------------------------------------------- #
# 7/8. Opt-in: frontend build, bundle validate
# --------------------------------------------------------------------------- #
def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def check_frontend(res: Result) -> None:
    print(f"{C.B}▶ Frontend build (npm run build){C.X}")
    fe = REPO / "apps" / "lakebase-lab-console" / "frontend"
    if not shutil.which("npm"):
        res.warn("npm not found; skipped frontend build")
        print(f"  {C.Y}⚠{C.X} npm not found")
        return
    if not (fe / "node_modules").is_dir():
        res.warn("frontend/node_modules missing; run `npm install` first")
        print(f"  {C.Y}⚠{C.X} node_modules missing (run npm install)")
        return
    code, out = run(["npm", "run", "build"], fe)
    if code == 0:
        print(f"  {C.G}✓{C.X} vite build succeeded")
    else:
        res.fail("frontend build failed (see output below)")
        print(f"  {C.R}✗{C.X} vite build failed\n{C.DIM}{out[-1500:]}{C.X}")


def check_bundle(res: Result) -> None:
    print(f"{C.B}▶ Databricks bundle validate{C.X}")
    if not shutil.which("databricks"):
        res.warn("databricks CLI not found; skipped bundle validate")
        print(f"  {C.Y}⚠{C.X} databricks CLI not found")
        return
    code, out = run(["databricks", "bundle", "validate", "-t", "dev"], REPO)
    if code == 0:
        print(f"  {C.G}✓{C.X} bundle config is valid")
    else:
        # Auth/profile problems are environmental, not a repo defect → warn.
        low = out.lower()
        if any(k in low for k in ("auth", "profile", "credential", "token", "cannot resolve", "host")):
            res.warn("bundle validate could not authenticate (environment, not repo)")
            print(f"  {C.Y}⚠{C.X} could not authenticate — check your CLI profile\n{C.DIM}{out[-800:]}{C.X}")
        else:
            res.fail("bundle validate failed")
            print(f"  {C.R}✗{C.X} invalid bundle\n{C.DIM}{out[-1200:]}{C.X}")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the Lakebase Workshop before commit/deploy.")
    ap.add_argument("--frontend", action="store_true", help="also build the React app")
    ap.add_argument("--bundle", action="store_true", help="also run `databricks bundle validate`")
    ap.add_argument("--full", action="store_true", help="run every check")
    args = ap.parse_args()

    print(f"{C.B}Lakebase Workshop validation{C.X}  {C.DIM}({rel(REPO) or REPO}){C.X}\n")
    res = Result()

    check_notebooks(res)
    check_structure(res)
    check_regressions(res)
    check_pg_catalog_queries(res)
    check_links(res)
    check_backend(res)
    check_secrets(res)
    if args.frontend or args.full:
        check_frontend(res)
    if args.bundle or args.full:
        check_bundle(res)

    print(f"\n{C.B}── Summary ─────────────────────────────{C.X}")
    print(f"  checks run : {res.checked}")
    print(f"  warnings   : {len(res.warnings)}")
    print(f"  failures   : {len(res.failures)}")
    for w in res.warnings:
        print(f"  {C.Y}⚠{C.X} {w}")
    for f in res.failures:
        print(f"  {C.R}✗{C.X} {f}")

    if res.failures:
        print(f"\n{C.R}VALIDATION FAILED{C.X} — fix the failures above before committing.")
        return 1
    print(f"\n{C.G}VALIDATION PASSED{C.X}" + (f" {C.Y}(with {len(res.warnings)} warning(s)){C.X}" if res.warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
