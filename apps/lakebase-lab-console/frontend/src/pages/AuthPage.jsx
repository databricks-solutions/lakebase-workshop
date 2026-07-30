import { useState, useEffect } from 'react'
import { api } from '../api'
import { Key, Database, RefreshCw, AlertCircle, Shield, Server, ChevronRight } from '../icons'
import LabBanner from '../LabBanner'

function CollapsibleSection({ title, icon, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card">
      <div
        className="card-header"
        style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setOpen(o => !o)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ChevronRight
            size={14}
            style={{
              transition: 'transform 0.2s',
              transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
              flexShrink: 0,
            }}
          />
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            {icon} {title}
          </h3>
        </div>
        {badge}
      </div>
      {open && children}
    </div>
  )
}

export default function AuthPage() {
  const [connInfo, setConnInfo] = useState(null)
  const [credential, setCredential] = useState(null)
  const [roles, setRoles] = useState([])
  const [grants, setGrants] = useState([])
  const [tls, setTls] = useState(null)
  const [loading, setLoading] = useState(true)
  const [credLoading, setCredLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    try {
      const [info, r, g, t] = await Promise.allSettled([
        api.authConnectionInfo(),
        api.authRoles(),
        api.authGrants(),
        api.authTls(),
      ])
      if (info.status === 'fulfilled') setConnInfo(info.value)
      if (r.status === 'fulfilled') setRoles(r.value)
      if (g.status === 'fulfilled') setGrants(g.value)
      if (t.status === 'fulfilled') setTls(t.value)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadAll() }, [])

  const generateCredential = async () => {
    setCredLoading(true)
    try {
      const cred = await api.authCredential()
      setCredential(cred)
    } catch (e) {
      setError(e.message)
    }
    setCredLoading(false)
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Authentication, Security & Compliance</h2>
            <p>
              Explore Lakebase's OAuth credential system, inspect JWT tokens, view database roles
              and grants, get connection details for external tools, and review the security and
              compliance posture (encryption, network isolation, TLS).
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadAll} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="auth" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* Two-Layer Permission Model */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} /> Two-Layer Permission Model</h3>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>Layer</th><th>What It Controls</th><th>Managed Via</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><span className="badge badge-info">Workspace</span></td>
              <td>Who can create/delete projects, branches, resize compute</td>
              <td>Databricks workspace IAM</td>
            </tr>
            <tr>
              <td><span className="badge badge-warning">Database</span></td>
              <td>Who can read/write PostgreSQL tables, schemas, sequences</td>
              <td>SQL GRANT statements</td>
            </tr>
          </tbody>
        </table>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 12, lineHeight: 1.6 }}>
          Both layers are independent. A user can manage branches without table access, and vice versa.
          Both must be configured for full access.
        </p>
      </div>

      <div className="grid-2col">
        {/* Connection Info */}
        <div className="card">
          <div className="card-header">
            <h3><Server size={16} /> Connection Details</h3>
          </div>
          {connInfo ? (
            <div style={{ fontSize: 13 }}>
              <div className="detail-row">
                <span className="detail-label">Host</span>
                <span className="detail-value detail-value-mono" style={{ fontSize: 11 }}>{connInfo.host}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Port</span>
                <span className="detail-value detail-value-mono">{connInfo.port}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Database</span>
                <span className="detail-value detail-value-mono">{connInfo.database}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Username</span>
                <span className="detail-value detail-value-mono" style={{ fontSize: 11 }}>{connInfo.username}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">SSL Mode</span>
                <span className="detail-value">{connInfo.ssl_mode}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Password</span>
                <span className="detail-value" style={{ fontSize: 11, color: 'var(--text-muted)' }}>OAuth token (1-hour TTL)</span>
              </div>
            </div>
          ) : (
            <div className="empty-state empty-state-compact"><p>Loading...</p></div>
          )}
        </div>

        {/* OAuth Credential */}
        <div className="card">
          <div className="card-header">
            <h3><Key size={16} /> OAuth Credential</h3>
          </div>
          {!credential ? (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
                Generate a fresh database credential to inspect the JWT token.
              </p>
              <button className="btn btn-primary btn-sm" onClick={generateCredential} disabled={credLoading}>
                <Key size={14} /> {credLoading ? 'Generating...' : 'Generate Credential'}
              </button>
            </div>
          ) : (
            <div style={{ fontSize: 13 }}>
              <div className="detail-row">
                <span className="detail-label">Token Preview</span>
                <span className="detail-value td-mono" style={{ fontSize: 10, wordBreak: 'break-all' }}>{credential.token_preview}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Length</span>
                <span className="detail-value">{credential.token_length} chars</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Expires</span>
                <span className="detail-value" style={{ fontSize: 11 }}>{credential.expire_time}</span>
              </div>
              <div style={{ marginTop: 12 }}>
                <button className="btn btn-secondary btn-sm" onClick={generateCredential} disabled={credLoading} style={{ marginBottom: 8 }}>
                  <RefreshCw size={12} /> Regenerate
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* JWT Claims */}
      {credential?.jwt_claims && Object.keys(credential.jwt_claims).length > 0 && (
        <CollapsibleSection
          title="JWT Payload"
          icon={<Key size={16} />}
          badge={<span className="badge badge-info">{Object.keys(credential.jwt_claims).length} claims</span>}
          defaultOpen={false}
        >
          <table className="data-table">
            <thead>
              <tr><th>Claim</th><th>Value</th></tr>
            </thead>
            <tbody>
              {Object.entries(credential.jwt_claims).map(([k, v]) => (
                <tr key={k}>
                  <td className="td-mono-bold">{k}</td>
                  <td className="td-mono-xs" style={{ wordBreak: 'break-all' }}>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
            <div className="info-box info">
              <span style={{ fontWeight: 600 }}>sub:</span>
              <span>The identity the credential is minted for. In this shared app that is the app&apos;s Service Principal (not your personal user), which becomes the PostgreSQL role name.</span>
            </div>
            <div className="info-box info">
              <span style={{ fontWeight: 600 }}>exp:</span>
              <span>Token expiration (~1 hour from issue). Open connections remain active past expiry; only new logins are rejected.</span>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Roles */}
      <CollapsibleSection
        title="Database Roles"
        icon={<Database size={16} />}
        badge={<span className="badge badge-info">{roles.length} roles</span>}
        defaultOpen={false}
      >
        {roles.length === 0 ? (
          <div className="empty-state empty-state-compact">
            <p>{loading ? 'Loading roles...' : 'No roles found or not connected'}</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Role</th><th>Superuser</th><th>Can Login</th><th>Create DB</th><th>Create Role</th></tr>
            </thead>
            <tbody>
              {roles.map((r, i) => (
                <tr key={i}>
                  <td className="td-mono-bold" style={{ fontSize: 12 }}>{r.rolname}</td>
                  <td>{r.rolsuper ? <span className="badge badge-danger">Yes</span> : <span style={{ color: 'var(--text-muted)' }}>No</span>}</td>
                  <td>{r.rolcanlogin ? <span className="badge badge-success">Yes</span> : <span style={{ color: 'var(--text-muted)' }}>No</span>}</td>
                  <td>{r.rolcreatedb ? <span className="badge badge-info">Yes</span> : <span style={{ color: 'var(--text-muted)' }}>No</span>}</td>
                  <td>{r.rolcreaterole ? <span className="badge badge-info">Yes</span> : <span style={{ color: 'var(--text-muted)' }}>No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CollapsibleSection>

      {/* Grants */}
      <CollapsibleSection
        title="Schema Grants"
        icon={<Shield size={16} />}
        badge={<span className="badge badge-info">{grants.length} grants</span>}
        defaultOpen={false}
      >
        {grants.length === 0 ? (
          <div className="empty-state empty-state-compact">
            <p>{loading ? 'Loading grants...' : 'No explicit grants found (you\'re the owner, so you have implicit access)'}</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Table</th><th>Grantee</th><th>Privilege</th></tr>
            </thead>
            <tbody>
              {grants.map((g, i) => (
                <tr key={i}>
                  <td className="td-mono-bold">{g.table_name}</td>
                  <td className="td-mono-xs">{g.grantee}</td>
                  <td><span className="badge badge-cyan">{g.privilege_type}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CollapsibleSection>

      {/* Grant Examples + External Tools */}
      <div className="grid-2col">
        <CollapsibleSection title="Grant Examples" icon={null} defaultOpen={false}>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
            Run these via the SQL Playground or psql to grant access:
          </p>
          <div className="code-block">{`-- Grant read access to a user
GRANT USAGE ON SCHEMA <schema> TO "user@company.com";
GRANT SELECT ON ALL TABLES IN SCHEMA <schema>
  TO "user@company.com";

-- Grant full access to a Service Principal (for Apps)
GRANT ALL ON SCHEMA <schema> TO "<SP_CLIENT_ID>";
GRANT ALL ON ALL TABLES IN SCHEMA <schema>
  TO "<SP_CLIENT_ID>";
GRANT ALL ON ALL SEQUENCES IN SCHEMA <schema>
  TO "<SP_CLIENT_ID>";

-- Auto-grant for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA <schema>
  GRANT ALL ON TABLES TO "<SP_CLIENT_ID>";`}</div>
        </CollapsibleSection>

        <CollapsibleSection title="External Tools" icon={null} defaultOpen={false}>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
            Connect with psql, DBeaver, DataGrip, or any PostgreSQL client:
          </p>
          <div className="code-block">{`# Generate a token via CLI
TOKEN=$(databricks postgres \\
  generate-database-credential \\
  "projects/<project-id>/branches/production/endpoints/primary" \\
  --profile <profile> -o json \\
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Connect with psql
PGPASSWORD="$TOKEN" psql \\
  -h <endpoint-host> \\
  -U <your-email> \\
  -d databricks_postgres \\
  --set=sslmode=require`}</div>
          <div className="info-box warning" style={{ marginTop: 12 }}>
            <span style={{ fontWeight: 600 }}>Token TTL:</span>
            <span>OAuth tokens expire after ~1 hour. Use a password command or connection pool with auto-refresh for long-running sessions.</span>
          </div>
          <div className="info-box info" style={{ marginTop: 10 }}>
            <span style={{ fontWeight: 600 }}>Connection limits:</span>
            <span>A connection may stay open up to ~3 days total and is closed after ~24 hours idle, regardless of token TTL. OAuth is per-connection; for a shared pooler (PgBouncer) you must use a stored password role, since a rotating token can't authenticate pooled connections.</span>
          </div>
        </CollapsibleSection>
      </div>

      {/* Security & Compliance */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} /> Security & Compliance</h3>
          {tls && (
            <span className={`badge ${tls.ssl === true ? 'badge-success' : tls.ssl === false ? 'badge-danger' : 'badge-info'}`}>
              {tls.ssl === true ? 'TLS active' : tls.ssl === false ? 'No TLS' : 'TLS unknown'}
            </span>
          )}
        </div>

        {/* Live TLS status */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Encryption in transit (this connection)</div>
          {tls ? (
            tls.ssl === true ? (
              <div style={{ fontSize: 13 }}>
                <div className="detail-row">
                  <span className="detail-label">TLS</span>
                  <span className="detail-value"><span className="badge badge-success">Enabled</span></span>
                </div>
                {tls.version && (
                  <div className="detail-row">
                    <span className="detail-label">Version</span>
                    <span className="detail-value detail-value-mono">{tls.version}</span>
                  </div>
                )}
                {tls.cipher && (
                  <div className="detail-row">
                    <span className="detail-label">Cipher</span>
                    <span className="detail-value detail-value-mono" style={{ fontSize: 11 }}>{tls.cipher}</span>
                  </div>
                )}
                {tls.bits != null && (
                  <div className="detail-row">
                    <span className="detail-label">Key bits</span>
                    <span className="detail-value detail-value-mono">{tls.bits}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Status:</span>
                <span>{tls.note || 'TLS status unavailable for this connection.'} All Lakebase connections require <code>sslmode=require</code>.</span>
              </div>
            )
          ) : (
            <div className="empty-state empty-state-compact"><p>{loading ? 'Checking TLS...' : 'TLS status unavailable'}</p></div>
          )}
        </div>

        {/* Encryption at rest / CMK */}
        <div className="info-box info">
          <span style={{ fontWeight: 600 }}>Encryption at rest:</span>
          <span>Data is always encrypted at rest with Databricks-managed keys. Customer-managed keys (CMK) are available on the Enterprise tier for projects that require control of the encryption key.</span>
        </div>

        {/* Network isolation / Private Link */}
        <div className="info-box info" style={{ marginTop: 10 }}>
          <span style={{ fontWeight: 600 }}>Network isolation:</span>
          <span>All traffic is TLS-encrypted. For performance-intensive or private connectivity, inbound Private Link keeps traffic off the public internet between your VPC/VNet and the Lakebase endpoint.</span>
        </div>

        {/* Compliance */}
        <div className="info-box info" style={{ marginTop: 10 }}>
          <span style={{ fontWeight: 600 }}>Compliance:</span>
          <span>Lakebase inherits the workspace's compliance security profile. Confirm the specific certifications available for your region and tier with the Lakebase Security FAQ before storing regulated data.</span>
        </div>

        {/* Limitation: audit logs */}
        <div className="info-box warning" style={{ marginTop: 10 }}>
          <span style={{ fontWeight: 600 }}>Limitation — audit logs:</span>
          <span>Per-statement Postgres audit logging is not yet available. Track privileged access at the workspace layer (IAM / system tables) and via the roles &amp; grants above.</span>
        </div>

        {/* Data API governance caveat */}
        <div className="info-box danger" style={{ marginTop: 10 }}>
          <span style={{ fontWeight: 600 }}>Data API governance:</span>
          <span>The Data API talks directly to Postgres and is governed by Postgres roles + row-level security, <strong>not</strong> Unity Catalog. Enable RLS on every exposed table and never expose data through the project owner account.</span>
        </div>
      </div>
    </div>
  )
}
