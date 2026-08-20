#!/usr/bin/env bash
#
# Lakebase Workshop — Getting Started
#
# Run this after cloning the repo. It handles everything:
#   1. Installs requirements
#   2. Connects you to your Databricks workspace
#   3. Validates your environment
#   4. Deploys content (and optionally the shared Lab Console app)
#

set -euo pipefail

BOLD="\033[1m"
DIM="\033[2m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE="lakebase-workshop"
APP_NAME="lakebase-lab-console"

banner() {
  echo ""
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}${CYAN}  Lakebase Autoscaling Workshop${RESET}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
}

step() { echo -e "\n${BOLD}${CYAN}▸ $1${RESET}"; }
info() { echo -e "  ${DIM}$1${RESET}"; }
ok()   { echo -e "  ${GREEN}✓ $1${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠ $1${RESET}"; }
fail() { echo -e "  ${RED}✗ $1${RESET}"; exit 1; }
ask()  { echo -en "  ${BOLD}$1${RESET} "; }

# Vite 6 (the Lab Console frontend) needs Node 18+.
NODE_MIN_MAJOR=18

node_major() {
  local ver
  ver="$(node --version 2>/dev/null || true)"
  ver="${ver#v}"
  echo "${ver%%.*}"
}

node_is_ok() {
  command -v npm >/dev/null 2>&1 || return 1
  command -v node >/dev/null 2>&1 || return 1
  local major
  major="$(node_major)"
  [[ "$major" =~ ^[0-9]+$ ]] || return 1
  [[ "$major" -ge "$NODE_MIN_MAJOR" ]]
}

_refresh_node_path() {
  if command -v brew >/dev/null 2>&1; then
    local prefix
    prefix="$(brew --prefix 2>/dev/null || true)"
    if [[ -n "$prefix" && -d "$prefix/bin" ]]; then
      export PATH="$prefix/bin:$PATH"
    fi
  fi
  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    . "$HOME/.nvm/nvm.sh"
  fi
  hash -r 2>/dev/null || true
}

# Install Node.js if missing or too old. Used when deploying the Lab Console so
# participants don't have to install it as a separate prerequisite.
ensure_nodejs() {
  if node_is_ok; then
    ok "Node.js $(node --version)"
    return 0
  fi

  if command -v node >/dev/null 2>&1; then
    warn "Node.js $(node --version) is too old — the frontend build needs v${NODE_MIN_MAJOR}+"
  else
    info "Node.js ${NODE_MIN_MAJOR}+ is needed to build the Lab Console UI."
  fi

  echo ""
  ask "Install Node.js now? (Y/n):"
  read -r INSTALL_NODE
  INSTALL_NODE="${INSTALL_NODE:-Y}"
  if [[ ! "$INSTALL_NODE" =~ ^[Yy] ]]; then
    return 1
  fi

  if command -v brew >/dev/null 2>&1; then
    info "Installing Node.js with Homebrew (this can take a minute)..."
    if brew list node >/dev/null 2>&1; then
      brew upgrade node || true
    else
      brew install node || true
    fi
  elif [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    info "Installing Node.js 20 via nvm..."
    # shellcheck disable=SC1090
    . "$HOME/.nvm/nvm.sh"
    nvm install 20 && nvm use 20 || true
  elif command -v apt-get >/dev/null 2>&1; then
    info "Installing Node.js with apt-get (may need your password)..."
    sudo apt-get update -qq && sudo apt-get install -y nodejs npm || true
  else
    warn "No supported package manager found (Homebrew, nvm, or apt)."
  fi

  _refresh_node_path

  if node_is_ok; then
    ok "Node.js $(node --version) installed"
    return 0
  fi

  if command -v node >/dev/null 2>&1; then
    warn "Node.js is now $(node --version), but the build needs v${NODE_MIN_MAJOR}+"
  else
    warn "Could not install Node.js automatically."
  fi
  info "Install Node.js ${NODE_MIN_MAJOR}+ from https://nodejs.org (or: brew install node), then re-run this script."
  return 1
}

banner

# ─────────────────────────────────────────────────────────────────────────────
# 1. Check for Python & pip
# ─────────────────────────────────────────────────────────────────────────────

step "Checking your environment"

if ! command -v python3 &>/dev/null; then
  fail "Python 3 is required but not installed. Install it from https://python.org"
fi
ok "Python $(python3 --version 2>&1 | awk '{print $2}')"

PIP_CMD="pip3"
if ! command -v pip3 &>/dev/null; then
  if command -v pip &>/dev/null; then
    PIP_CMD="pip"
  else
    fail "pip is required but not installed."
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. Install requirements
# ─────────────────────────────────────────────────────────────────────────────

step "Python dependencies"
info "The workshop requires: databricks-cli, databricks-sdk, psycopg"
echo ""
ask "Install/update Python requirements now? (Y/n):"
read -r INSTALL_DEPS
INSTALL_DEPS="${INSTALL_DEPS:-Y}"

if [[ "$INSTALL_DEPS" =~ ^[Yy] ]]; then
  echo ""
  if ! $PIP_CMD install -q "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null; then
    info "Retrying with --break-system-packages (PEP 668)..."
    $PIP_CMD install -q --break-system-packages "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null || true
  fi
  ok "Python packages installed"
else
  info "Skipping. Make sure you have the required packages installed."
fi

# Check for Databricks CLI
if ! command -v databricks &>/dev/null; then
  echo ""
  warn "Databricks CLI is not installed."
  info "Install it:"
  info "  macOS:   brew install databricks/tap/databricks"
  info "  pip:     pip install databricks-cli"
  info "  docs:    https://docs.databricks.com/en/dev-tools/cli/install.html"
  echo ""
  ask "Press Enter once you've installed it, or Ctrl+C to exit..."
  read -r

  if ! command -v databricks &>/dev/null; then
    fail "Databricks CLI still not found. Please install it and re-run this script."
  fi
fi
ok "Databricks CLI $(databricks --version 2>&1 | head -1)"

# Node.js is only required to build the Lab Console UI (deploy option 2 below).
# setup.sh installs it then if missing — no need to fail here.
if node_is_ok; then
  ok "Node.js $(node --version)"
elif command -v node >/dev/null 2>&1; then
  warn "Node.js $(node --version) is below v${NODE_MIN_MAJOR} — setup will upgrade it if you deploy the app"
else
  info "Node.js not found yet — setup will install it if you deploy the Lab Console app"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Connect to workspace
# ─────────────────────────────────────────────────────────────────────────────

step "Connect to your Databricks workspace"

EXISTING=$(databricks auth profiles 2>/dev/null | grep "YES" | head -5 || true)

if [[ -z "$EXISTING" ]]; then
  info "No authenticated workspaces found. Let's connect to one."
fi

if [[ -n "$EXISTING" ]]; then
  echo ""
  info "Found existing authenticated workspaces:"
  echo ""
  echo -e "  ${DIM}Name               Host                                             ${RESET}"
  echo -e "  ${DIM}─────────────────  ─────────────────────────────────────────────────${RESET}"
  databricks auth profiles 2>/dev/null | grep "YES" | while read -r line; do
    echo -e "  ${GREEN}$line${RESET}"
  done
  echo ""
  ask "Use one of these? Enter the profile name, or type NEW to add a workspace:"
  read -r PROFILE_CHOICE

  if [[ "$PROFILE_CHOICE" != "NEW" && "$PROFILE_CHOICE" != "new" && -n "$PROFILE_CHOICE" ]]; then
    PROFILE="$PROFILE_CHOICE"
    WORKSPACE_HOST=$(databricks auth profiles 2>/dev/null | grep "$PROFILE" | awk '{print $2}')
  fi
fi

if [[ "$PROFILE" == "lakebase-workshop" ]] || [[ "${PROFILE_CHOICE:-}" == "NEW" ]] || [[ "${PROFILE_CHOICE:-}" == "new" ]]; then
  echo ""
  ask "Enter your Databricks workspace URL:"
  read -r WORKSPACE_URL
  WORKSPACE_URL="${WORKSPACE_URL%/}"

  if [[ -z "$WORKSPACE_URL" ]]; then
    fail "Workspace URL is required."
  fi

  if [[ ! "$WORKSPACE_URL" =~ ^https:// ]]; then
    WORKSPACE_URL="https://$WORKSPACE_URL"
  fi

  WORKSPACE_HOST="$WORKSPACE_URL"

  ask "Profile name (default: lakebase-workshop):"
  read -r CUSTOM_PROFILE
  [[ -n "$CUSTOM_PROFILE" ]] && PROFILE="$CUSTOM_PROFILE"

  echo ""
  info "Opening your browser to authenticate..."
  info "Log in with your Databricks credentials."
  echo ""
  databricks auth login --host "$WORKSPACE_URL" --profile "$PROFILE"
fi

# Validate
VALID=$(databricks auth profiles 2>/dev/null | grep "$PROFILE" | grep -c "YES" || true)
if [[ "$VALID" -eq 0 ]]; then
  echo ""
  fail "Authentication failed for profile '$PROFILE'. Try running: databricks auth login --host <your-url> --profile $PROFILE"
fi

WORKSPACE_HOST=$(databricks auth profiles 2>/dev/null | grep "$PROFILE" | awk '{print $2}')
ok "Connected to $WORKSPACE_HOST"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Validate Lakebase access
# ─────────────────────────────────────────────────────────────────────────────

step "Validating Lakebase access"

if databricks postgres list-projects --profile "$PROFILE" &>/dev/null; then
  ok "Lakebase Autoscaling is available on this workspace"
else
  warn "Could not verify Lakebase access. This may be a permissions issue,"
  warn "or Lakebase may not be enabled on this workspace."
  info "The workshop requires Lakebase Autoscaling. Contact your workspace admin if needed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Save config & configure DABs
# ─────────────────────────────────────────────────────────────────────────────

step "Saving configuration"

# If this checkout was previously pointed at a different workspace, drop local
# DAB Terraform state. Otherwise Apps deploy fails with workspace_id mismatch
# (stale provider_config from the prior workspace). State is gitignored and
# per-machine; remote state in each workspace is independent.
PREV_HOST=""
if [[ -f "$SCRIPT_DIR/.workshop-config" ]]; then
  # shellcheck disable=SC1091
  PREV_HOST=$(grep '^WORKSPACE_HOST=' "$SCRIPT_DIR/.workshop-config" 2>/dev/null | cut -d= -f2- || true)
fi
if [[ -n "$PREV_HOST" && "$PREV_HOST" != "$WORKSPACE_HOST" ]]; then
  warn "Workspace changed ($PREV_HOST → $WORKSPACE_HOST)"
  info "Clearing local bundle Terraform state so deploy targets the new workspace"
  find "$SCRIPT_DIR/.databricks/bundle" -type f \( -name 'terraform.tfstate' -o -name 'terraform.tfstate.backup' -o -name 'plan' \) -delete 2>/dev/null || true
fi

DAB_YAML="$SCRIPT_DIR/databricks.yml"
# Always rewrite target profiles (not a one-shot <your-profile> placeholder), so
# the same clone can be reused across customer workspaces.
python3 -c "
import re
path = '$DAB_YAML'
profile = '''$PROFILE'''
content = open(path).read()
content = content.replace('<your-profile>', profile)
content = re.sub(r'(^[ \t]*profile:\s*)\S+', r'\g<1>' + profile, content, flags=re.M)
open(path, 'w').write(content)
" 2>/dev/null || true
ok "databricks.yml configured with profile: $PROFILE"

USER_EMAIL=$(databricks current-user me --profile "$PROFILE" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])" 2>/dev/null || echo "<your-email>")

# Derive the Lakebase project ID (for display only — the app resolves it dynamically)
PROJECT_ID=$(python3 -c "
import re
email = '$USER_EMAIL'
name = email.split('@')[0]
name = re.sub(r'[^a-z0-9-]', '-', name.lower())
name = re.sub(r'-+', '-', name).strip('-')
print(f'lakebase-lab-{name}')
" 2>/dev/null || echo "lakebase-lab-unknown")

# Write config file for reference
cat > "$SCRIPT_DIR/.workshop-config" <<EOF
PROFILE=$PROFILE
WORKSPACE_HOST=$WORKSPACE_HOST
PROJECT_ID=$PROJECT_ID
APP_NAME=$APP_NAME
EOF
ok "Config saved to .workshop-config"
ok "App name: $APP_NAME (shared by all users)"

# ─────────────────────────────────────────────────────────────────────────────
# 6. Deploy to workspace
# ─────────────────────────────────────────────────────────────────────────────

DEPLOYED_APP=false

# Pre-flight check: the Lab Console app binds to a Lakebase project as its
# `postgres` resource. If the facilitator hasn't created their project yet,
# the resource attachment + SP grant steps below will fail with confusing
# "No endpoints" errors. Always try to auto-create; if that fails, tell them
# to run the setup notebook (the same work the old "M" path asked them to do).
tell_run_setup_notebook() {
  echo ""
  info "Auto-create could not finish. Run this notebook in your Databricks workspace (all cells):"
  info "  Workspace > Users > ${USER_EMAIL:-<your-email>} > .bundle > lakebase-workshop > dev > files > notebooks > 00_Setup_Lakebase_Project"
  info ""
  info "Then re-run: ${BOLD}bash setup.sh${RESET}"
  echo ""
}

ensure_lakebase_project() {
  local project_id="$1"
  local schema="$2"
  local profile="$3"

  step "Checking your Lakebase project"

  if databricks postgres get-project "projects/$project_id" --profile "$profile" &>/dev/null; then
    ok "Lakebase project '$project_id' exists"
    return 0
  fi

  echo ""
  warn "No Lakebase project found for your account."
  info "Project ID: $project_id"
  info "The Lab Console app needs an existing Lakebase project to attach to."
  info "Creating it now (~2-3 min)..."
  echo ""

  if ! python3 -c "import databricks.sdk, psycopg" &>/dev/null; then
    info "Installing databricks-sdk + psycopg (needed to auto-create the project)..."
    if ! $PIP_CMD install -q "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null; then
      $PIP_CMD install -q --break-system-packages "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null || true
    fi
    if ! python3 -c "import databricks.sdk, psycopg" &>/dev/null; then
      tell_run_setup_notebook
      fail "Could not install databricks-sdk + psycopg, so the project could not be created automatically."
    fi
  fi

  info "Creating Lakebase project '$project_id' (1-3 min)..."

  if python3 - "$project_id" "$schema" "$profile" "$SCRIPT_DIR" <<'PYEOF'
import os
import sys
import time

project_id = sys.argv[1]
schema = sys.argv[2]
profile = sys.argv[3]
script_dir = sys.argv[4]

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Project, ProjectSpec

w = WorkspaceClient(profile=profile)

try:
    w.postgres.get_project(name=f"projects/{project_id}")
    print(f"  ✓ Project already exists")
except Exception:
    print(f"  Creating project...")
    operation = w.postgres.create_project(
        project=Project(
            spec=ProjectSpec(
                display_name=f"Lakebase Workshop: {project_id}",
                pg_version="17",
            )
        ),
        project_id=project_id,
    )
    operation.wait()
    print(f"  ✓ Project created")

print(f"  Waiting for production endpoint to become available...")
endpoint = None
# IDLE means scaled to zero, which only wakes on connect — treat it as ready.
for _ in range(90):
    try:
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{project_id}/branches/production"
        ))
        if endpoints:
            ep = w.postgres.get_endpoint(name=endpoints[0].name)
            state = str(getattr(ep.status, "current_state", "")).upper()
            if any(ready in state for ready in ("ACTIVE", "IDLE", "DEGRADED")):
                endpoint = ep
                print(f"  ✓ Endpoint available ({state.split('.')[-1]}): {ep.status.hosts.host}")
                break
    except Exception:
        pass
    time.sleep(5)

if endpoint is None:
    print("  ✗ Endpoint is still provisioning; check the Lakebase UI")
    sys.exit(1)

print(f"  Seeding schema '{schema}'...")
import psycopg

seed_path = os.path.join(script_dir, "bootstrap", "seed.sql")
with open(seed_path) as f:
    seed_sql = f.read().replace("{schema}", schema)

cred = w.postgres.generate_database_credential(endpoint=endpoint.name)
user_email = w.current_user.me().user_name

with psycopg.connect(
    host=endpoint.status.hosts.host,
    dbname="databricks_postgres",
    user=user_email,
    password=cred.token,
    sslmode="require",
) as conn:
    with conn.cursor() as cur:
        cur.execute(seed_sql)
    conn.commit()

print(f"  ✓ Schema seeded")
PYEOF
  then
    ok "Lakebase project ready"
    return 0
  else
    tell_run_setup_notebook
    fail "Auto-create failed. The rest of setup cannot attach the Lab Console until this project exists."
  fi
}

step "Deploy to workspace"
info "What would you like to deploy?"
echo ""
echo -e "    ${BOLD}1)${RESET} Labs only      — notebooks and lab files (no app compute)"
echo -e "    ${BOLD}2)${RESET} Labs + App     — everything, including the shared Lab Console app"
echo ""
ask "Choice (1/2):"
read -r DEPLOY_CHOICE
DEPLOY_CHOICE="${DEPLOY_CHOICE:-1}"

if [[ "$DEPLOY_CHOICE" == "2" ]]; then
  PG_SCHEMA=$(python3 -c "
import re
email = '$USER_EMAIL'
name = email.split('@')[0]
name = re.sub(r'[^a-z0-9-]', '-', name.lower())
name = re.sub(r'-+', '-', name).strip('-')
print(f'lakebase_lab_{name.replace(\"-\", \"_\")}')
" 2>/dev/null || echo "")

  ensure_lakebase_project "$PROJECT_ID" "$PG_SCHEMA" "$PROFILE"

  # The app's UI is a build artifact that is not committed (frontend/dist is
  # gitignored), so it must be built here or the deployed app serves no UI.
  FRONTEND_DIR="$SCRIPT_DIR/apps/lakebase-lab-console/frontend"
  FRONTEND_BUILT=false

  ensure_nodejs || true

  if [[ -f "$FRONTEND_DIR/package.json" ]]; then
    if command -v npm >/dev/null 2>&1; then
      info "Building frontend (this takes ~30s)..."
      BUILD_LOG="$(mktemp -t lakebase-frontend-build.XXXXXX)"
      if (cd "$FRONTEND_DIR" && npm install --silent && npm run build --silent) \
           >"$BUILD_LOG" 2>&1 && [[ -f "$FRONTEND_DIR/dist/index.html" ]]; then
        FRONTEND_BUILT=true
        rm -f "$BUILD_LOG"
        ok "Frontend built"
      else
        warn "Frontend build failed. Last lines of the build output:"
        tail -15 "$BUILD_LOG" 2>/dev/null | sed 's/^/      /'
        info "Full build log: $BUILD_LOG"
      fi
    else
      warn "Node.js / npm was not found, so the app's UI cannot be built."
      info "Install Node.js (it includes npm), then re-run this script:"
      info "  https://nodejs.org  —  or: brew install node"
    fi
  else
    warn "Frontend sources not found at $FRONTEND_DIR"
  fi

  if [[ "$FRONTEND_BUILT" != true ]]; then
    echo ""
    warn "Deploying the app now would give you a working API with no user interface —"
    warn "opening it in a browser shows a 'UI not built' page instead of the console."
    info "The notebook labs do not use the app, so they are unaffected."
    echo ""
    ask "Deploy the app anyway, without its UI? (y/N):"
    read -r DEPLOY_WITHOUT_UI
    if [[ ! "${DEPLOY_WITHOUT_UI:-N}" =~ ^[Yy] ]]; then
      info "Skipping the app — deploying the labs only."
      info "After installing Node.js, get the app with:"
      info "  bash setup.sh   (choose option 2)"
      DEPLOY_CHOICE=1
    fi
  fi
fi

info "Deploying bundle..."
if databricks bundle deploy --target dev --profile "$PROFILE"; then
  ok "Deployed to workspace"
  echo ""
  info "Find your content at:"
  info "  /Workspace/Users/${USER_EMAIL}/.bundle/lakebase-workshop/dev/files/"

  if [[ "$DEPLOY_CHOICE" == "2" ]]; then
    echo ""
    info "Starting app and deploying source code..."
    if databricks bundle run lakebase_lab_console --target dev --profile "$PROFILE"; then
      ok "App deployed and running"
      DEPLOYED_APP=true
    else
      warn "App deploy failed — you can deploy later with:"
      info "  databricks bundle run lakebase_lab_console --target dev --profile $PROFILE"
    fi
  fi
else
  warn "Bundle deploy failed. You can retry manually:"
  info "  databricks bundle deploy --target dev --profile $PROFILE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6b. Attach Lakebase resource + SP grants (facilitator's project)
# ─────────────────────────────────────────────────────────────────────────────

reattach_lakebase_resource() {
  local app_name="$1"
  local project_id="$2"
  local profile="$3"

  step "Attaching Lakebase resource to app"

  BRANCH_PATH="projects/${project_id}/branches/production"

  # Look up the database resource path (the API uses generated IDs, not the PG database name)
  DB_PATH=$(databricks postgres list-databases "$BRANCH_PATH" --profile "$profile" -o json 2>/dev/null \
    | python3 -c "
import sys, json
for db in json.load(sys.stdin):
    if db.get('status', {}).get('postgres_database') == 'databricks_postgres':
        print(db['name'])
        break
" 2>/dev/null || echo "")

  if [[ -z "$DB_PATH" ]]; then
    warn "Could not find database resource path for project $project_id"
    info "You may need to attach the postgres resource manually in the Apps UI"
    return 1
  fi
  info "Database path: $DB_PATH"

  PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'app': {
        'resources': [{
            'name': 'lakebase-db',
            'postgres': {
                'branch': '$BRANCH_PATH',
                'database': '$DB_PATH',
                'permission': 'CAN_CONNECT_AND_CREATE'
            }
        }]
    },
    'update_mask': 'resources'
}))
" 2>/dev/null)

  # Use the CLI's authenticated API command so the OAuth token stays in-process
  # (never placed on the command line / visible via `ps`, and no raw error body
  # is echoed to the terminal or logs).
  if databricks api post "/api/2.0/apps/${app_name}/update" \
       --profile "$profile" --json "$PAYLOAD" >/dev/null 2>&1; then
    ok "Postgres resource attached (project: $project_id)"
    return 0
  else
    warn "Resource attachment failed"
    info "You may need to attach the postgres resource manually in the Apps UI:"
    info "  Compute → Apps → $app_name → Edit → Add resource → Database"
    info "  Select project '$project_id', branch 'production', permission 'Can connect and create'"
    return 1
  fi
}

grant_sp_access() {
  local project_id="$1"
  local schema="$2"
  local profile="$3"

  step "Granting SP access to facilitator's Lakebase project"

  if ! python3 -c "import databricks.sdk" &>/dev/null; then
    warn "databricks-sdk not found in local Python — installing..."
    if ! $PIP_CMD install -q "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null; then
      $PIP_CMD install -q --break-system-packages "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" 2>/dev/null || true
    fi
    if ! python3 -c "import databricks.sdk" &>/dev/null; then
      warn "Could not install databricks-sdk. SP grants will be handled"
      info "automatically when each user runs 00_Setup_Lakebase_Project (Step 6)."
      return 1
    fi
  fi

  python3 - "$project_id" "$schema" "$profile" <<'PYEOF'
import sys

project_id = sys.argv[1]
schema = sys.argv[2]
profile = sys.argv[3]

from databricks.sdk import WorkspaceClient

w = WorkspaceClient(profile=profile)

app = w.apps.get(name="lakebase-lab-console")
sp_id = getattr(app, 'effective_service_principal_client_id', None) or app.service_principal_client_id
print(f"  SP Client ID: {sp_id}")

# Control-plane ACL. Attaching the postgres resource only covers the data plane;
# branch/endpoint management needs CAN_MANAGE on the project itself.
from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel

try:
    w.permissions.update(
        request_object_type="database-projects",
        request_object_id=project_id,
        access_control_list=[
            AccessControlRequest(
                service_principal_name=sp_id,
                permission_level=PermissionLevel.CAN_MANAGE,
            )
        ],
    )
    print(f"  ✓ Granted CAN_MANAGE on project '{project_id}' to SP")
except Exception as e:
    print(f"  ⚠ Could not grant project ACL: {e}")
    print(f"    Branch Manager will fail until the SP has 'Can Manage' on the project.")

endpoints = list(w.postgres.list_endpoints(
    parent=f"projects/{project_id}/branches/production"
))
if not endpoints:
    print(f"  ⚠ No endpoints for {project_id}/production — run 00_Setup first")
    sys.exit(1)

ep = w.postgres.get_endpoint(name=endpoints[0].name)
cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)

import psycopg
user_email = w.current_user.me().user_name
conn = psycopg.connect(
    host=ep.status.hosts.host,
    dbname="databricks_postgres",
    user=user_email,
    password=cred.token,
    sslmode="require",
)
with conn.cursor() as cur:
    # The databricks_auth extension provides databricks_create_role().
    # It's per-database and idempotent — safe to run on every setup.
    cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
    print(f"  ✓ databricks_auth extension ready")

    try:
        cur.execute(f"SELECT databricks_create_role('{sp_id}', 'service_principal')")
        print(f"  ✓ Created OAuth role for SP")
    except Exception as e:
        if 'already exists' in str(e):
            conn.rollback()
            print(f"  ✓ OAuth role already exists (created by resource attachment)")
        else:
            raise
    cur.execute(f'GRANT ALL ON SCHEMA {schema} TO "{sp_id}"')
    cur.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA {schema} TO "{sp_id}"')
    cur.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA {schema} TO "{sp_id}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON TABLES TO "{sp_id}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON SEQUENCES TO "{sp_id}"')
conn.commit()
conn.close()
print(f"  ✓ SP granted access to schema: {schema}")
PYEOF
}

if [[ "$DEPLOYED_APP" == "true" ]]; then
  reattach_lakebase_resource "$APP_NAME" "$PROJECT_ID" "$PROFILE" || true

  if [[ -n "${PG_SCHEMA:-}" ]]; then
    grant_sp_access "$PROJECT_ID" "$PG_SCHEMA" "$PROFILE" || true
  else
    warn "Could not derive schema name — run SP grants from the setup notebook"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. Done — show next steps
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}${GREEN}  Workshop Flow${RESET}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Step 1: Run the foundation${RESET}"
echo -e "  Open ${BOLD}notebooks/00_Setup_Lakebase_Project${RESET} and click Run All."
echo -e "  This creates your Lakebase project and seeds your user schema."
echo ""
echo -e "  ${BOLD}Step 2: Pick a lab path${RESET}"
echo -e "  Each path is independent — choose based on your interest:"
echo ""
echo -e "    ${CYAN} 1. labs/data-operations/${RESET}         CRUD, JSONB, transactions, advanced SQL"
echo -e "    ${CYAN} 2. labs/reverse-etl/${RESET}             Sync Delta tables into Lakebase"
echo -e "    ${CYAN} 3. labs/lakehouse-sync/${RESET}          Lakebase → Delta CDC sync / Change Data Feed (Public Preview)"
echo -e "    ${CYAN} 4. labs/development-experience/${RESET}  Branching, autoscaling, scale-to-zero"
echo -e "    ${CYAN} 5. labs/observability/${RESET}           pg_stat views, index analysis, monitoring"
echo -e "    ${CYAN} 6. labs/authentication/${RESET}          OAuth tokens, roles, permissions"
echo -e "    ${CYAN} 7. labs/backup-recovery/${RESET}         Checkpoint branches, snapshots, PITR"
echo -e "    ${CYAN} 8. labs/agentic-memory/${RESET}          Persistent AI agent memory"
echo -e "    ${CYAN} 9. labs/online-feature-store/${RESET}    Real-time ML feature serving"
echo -e "    ${CYAN}10. labs/app-deployment/${RESET}          Full-stack Lab Console app (capstone)"
echo -e "    ${CYAN}11. labs/data-api/${RESET}                 PostgREST REST access, OAuth bearer tokens, RLS"
echo -e "    ${CYAN}12. labs/lakebase-search/${RESET}          Vector + keyword search with hybrid RRF ranking (Beta)"
echo ""
echo -e "  ${DIM}Workspace:   $WORKSPACE_HOST${RESET}"
echo -e "  ${DIM}Profile:     $PROFILE${RESET}"
echo -e "  ${DIM}Project ID:  $PROJECT_ID (yours — each user gets their own)${RESET}"
if [[ "$DEPLOYED_APP" == "true" ]]; then
  echo -e "  ${DIM}App:         $APP_NAME (running — shared by all workshop participants)${RESET}"
else
  echo -e "  ${DIM}App:         not deployed — deploy later with:${RESET}"
  echo -e "  ${DIM}             databricks bundle run lakebase_lab_console --target dev --profile $PROFILE${RESET}"
fi
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
