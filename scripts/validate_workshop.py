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
}

# Files excluded from the regression grep (they legitimately quote old facts).
REGRESSION_EXCLUDE = {
    "docs/LAKEBASE_AUDIT.md",
    "scripts/validate_workshop.py",
}

# Stale facts that must not reappear in learner-facing content. (label, regex)
# Extend this list whenever an audit corrects a hard fact.
REGRESSIONS: list[tuple[str, str]] = [
    ("autoscaling max was corrected to 64 CU (not 112)", r"\b112\s*CU\b"),
    ("autoscaling spread is <=16 CU (not 8)", r"spread[^.\n]{0,40}\b8\s*CU\b"),
    ("autoscaling range wording '0.5-32 CU' is stale", r"0\.5\s*[-\u2013]\s*32\s*CU"),
    ("restore window max is 30 days (not 35)", r"\b35[\s-]?day"),
    ("PITR SDK field is source_branch_time (not parent_timestamp)", r"parent_timestamp"),
    ("use 'Databricks Asset Bundle' (not 'Declarative Automation Bundle')", r"Declarative Automation Bundle"),
    ("project labs must link oltp/projects (not oltp/instances)", r"oltp/instances/"),
    ("lakehouse-sync is Public Preview / CDF (not 'Beta, UI-only')", r"Beta,\s*UI-only"),
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
# 6/7. Opt-in: frontend build, bundle validate
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
    check_links(res)
    check_backend(res)
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
