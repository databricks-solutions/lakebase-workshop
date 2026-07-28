import { useState, useEffect } from 'react'
import { api } from '../api'
import { useAppContext } from '../App'
import { getNotebookUrl, NOTEBOOK_MAP } from '../LabBanner'
import {
  Zap, GitBranch, Database, TrendingUp, Activity,
  Server, Bot, RefreshCw, Terminal,
  ExternalLink, Cpu, Table, Layers, Key, Shield, BookOpen
} from '../icons'

function cleanState(raw) {
  if (!raw) return 'unknown'
  const dot = raw.lastIndexOf('.')
  return dot >= 0 ? raw.slice(dot + 1) : raw
}

function QuickActionCard({ pageId, Icon, title, desc, onNavigate, config }) {
  const nbUrl = getNotebookUrl(config, pageId)
  return (
    <div className="quick-action-card-wrap">
      <button
        className="quick-action-card"
        onClick={() => onNavigate(pageId)}
        aria-label={`Open ${title}`}
      >
        <div className="qa-icon"><Icon size={20} /></div>
        <div className="qa-title">{title}</div>
        <div className="qa-desc">{desc}</div>
      </button>
      {nbUrl && (
        <a
          className="qa-notebook-link"
          href={nbUrl}
          target="_blank"
          rel="noopener noreferrer"
          title={`Open ${NOTEBOOK_MAP[pageId]?.label} notebook`}
          onClick={e => e.stopPropagation()}
        >
          <BookOpen size={12} /> Notebook
        </a>
      )}
    </div>
  )
}

export default function Dashboard({ onNavigate }) {
  const ctx = useAppContext()
  const [config, setConfig] = useState(null)
  const [dbStatus, setDbStatus] = useState(null)
  const [stats, setStats] = useState({})
  const [branches, setBranches] = useState([])
  const [endpoints, setEndpoints] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    Promise.allSettled([
      api.config().then(setConfig),
      api.dbtest().then(setDbStatus).catch((e) => setDbStatus({ db_connected: false, error: e.message })),
      api.tableStats().then(setStats).catch(() => setStats({})),
      api.listBranches().then(setBranches).catch(() => setBranches([])),
      api.listEndpoints('production').then(setEndpoints).catch(() => setEndpoints([])),
    ]).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const ep = endpoints[0] || {}
  const connected = dbStatus?.db_connected === true
  const totalRows = Object.values(stats).reduce((a, b) => a + (b > 0 ? b : 0), 0)

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Dashboard</h2>
            <p>Lakebase project overview and health</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'icon-spin' : ''} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Status Banner */}
      {dbStatus?.needs_setup ? (
        <div className="status-banner status-error">
          <div className="status-banner-left">
            <span className="pulse-dot pulse-red" />
            <div>
              <div className="status-banner-title">
                Lakebase Project Not Found
              </div>
              <div className="status-banner-detail">
                Run the setup notebook (<strong>00_Setup_Lakebase_Project</strong>) to create your
                Lakebase project and seed your schema. Once complete, refresh this page.
              </div>
              <div className="setup-hint">
                Expected project: {config?.project_id || 'unknown'}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className={`status-banner ${connected ? 'status-healthy' : 'status-error'}`}>
          <div className="status-banner-left">
            <span className={`pulse-dot ${connected ? 'pulse-green' : 'pulse-red'}`} />
            <div>
              <div className="status-banner-title">
                {connected ? 'Lakebase Connected' : 'Lakebase Disconnected'}
              </div>
              <div className="status-banner-detail">
                {config?.project_id || 'No project configured'}
                {ep.state && <> &middot; Compute: {cleanState(ep.state)}</>}
              </div>
              {!connected && dbStatus?.error && (
                <div className="error-detail">
                  {dbStatus.error}
                </div>
              )}
            </div>
          </div>
          <div className="status-banner-right">
            <span className="badge badge-info" title="Branch">{config?.branch_id || 'production'}</span>
            <span className="badge badge-cyan" title="Schema">{config?.schema || '...'}</span>
            {config?.user_email && (
              <span className="badge badge-info" title={config.user_email}>
                {config.user_email.split('@')[0]}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Key Metrics */}
      <div className="metrics-row metrics-row-4">
        <div className="metric-card">
          <div className="metric-icon"><Zap size={18} /></div>
          <div className="metric-value">{ep.min_cu ?? '--'}-{ep.max_cu ?? '--'}</div>
          <div className="metric-label">Compute (CU)</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><GitBranch size={18} /></div>
          <div className="metric-value">{branches.length}</div>
          <div className="metric-label">Branches</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Table size={18} /></div>
          <div className="metric-value">{Object.keys(stats).length}</div>
          <div className="metric-label">Tables</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Activity size={18} /></div>
          <div className="metric-value">{totalRows.toLocaleString()}</div>
          <div className="metric-label">Total Rows</div>
        </div>
      </div>

      {/* Table Stats + Endpoint */}
      <div className="grid-2col">
        <div className="card">
          <div className="card-header">
            <h3><Database size={16} /> Table Overview</h3>
          </div>
          {Object.keys(stats).length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Table size={28} /></div>
              <p>{connected ? 'Loading table stats...' : 'Connect to Lakebase to view tables'}</p>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Table</th><th style={{ textAlign: 'right' }}>Rows</th></tr>
              </thead>
              <tbody>
                {Object.entries(stats).map(([name, count]) => (
                  <tr key={name}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{config?.schema || ''}.{name}</td>
                    <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {count >= 0 ? count.toLocaleString() : <span className="badge badge-danger">error</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <h3><Server size={16} /> Endpoint Details</h3>
          </div>
          {ep.name ? (
            <div>
              <div className="detail-row">
                <span className="detail-label">Endpoint</span>
                <span className="detail-value detail-value-mono">{ep.name?.split('/').pop()}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">State</span>
                <span className={`badge ${ep.state?.includes('ACTIVE') ? 'badge-success' : 'badge-warning'}`}>
                  {cleanState(ep.state)}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Type</span>
                <span className="detail-value detail-value-mono">{ep.endpoint_type?.replace(/^.*\./, '') || '--'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Autoscaling</span>
                <span className="detail-value detail-value-mono">{ep.min_cu ?? '--'} - {ep.max_cu ?? '--'} CU</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Memory</span>
                <span className="detail-value detail-value-mono">{ep.min_cu != null ? `${(ep.min_cu * 2).toFixed(0)}-${(ep.max_cu * 2).toFixed(0)} GB` : '--'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Host</span>
                <span className="detail-value detail-value-mono">{ep.host || '--'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Database</span>
                <span className="detail-value detail-value-mono">{dbStatus?.info?.db || config?.database || 'databricks_postgres'}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">PG Version</span>
                <span className="detail-value detail-value-mono">{dbStatus?.info?.version?.split('(')[0]?.trim() || '--'}</span>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon"><Server size={28} /></div>
              <p>No endpoint data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <div className="card-header">
          <h3>Labs</h3>
          <span className="badge badge-info">
            Available in app and as notebooks
          </span>
        </div>
        <div className="quick-actions-grid">
          <QuickActionCard pageId="autoscale" Icon={TrendingUp} title="Autoscale Demo" desc="Spike traffic and watch compute scale in real time" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="branches" Icon={GitBranch} title="Branch Manager" desc="Create, review, and delete database branches" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="data" Icon={Database} title="Data Ops" desc="CRUD operations, JSONB queries, audit log" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="agent" Icon={Bot} title="Agent Memory" desc="Persistent AI agent session and message storage" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="observability" Icon={Activity} title="Observability" desc="PostgreSQL diagnostics, pg_stat views, connection pool" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="sync" Icon={RefreshCw} title="Synced Tables" desc="Sync Delta tables to Lakebase (Reverse ETL) and back to Unity Catalog" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="feature-store" Icon={Layers} title="Feature Store" desc="ML feature serving with online stores backed by Lakebase" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="auth" Icon={Key} title="Auth & Security" desc="OAuth credentials, JWT tokens, roles, grants, TLS & compliance" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="backup" Icon={Shield} title="Backup & Recovery" desc="Branch snapshots, PITR, disaster recovery" onNavigate={onNavigate} config={ctx?.config} />
          <QuickActionCard pageId="compute" Icon={Cpu} title="Compute Config" desc="Configure compute CU limits and view endpoints" onNavigate={onNavigate} config={ctx?.config} />
          <div className="quick-action-card-wrap">
            <button className="quick-action-card" onClick={() => onNavigate('api')} aria-label="Open API Tester">
              <div className="qa-icon"><Terminal size={20} /></div>
              <div className="qa-title">API Tester</div>
              <div className="qa-desc">Execute raw API calls against Lakebase</div>
            </button>
          </div>
          <div className="quick-action-card-wrap">
            <a
              className="quick-action-card"
              href="https://docs.databricks.com/aws/en/oltp/projects/"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open Lakebase documentation (external)"
            >
              <div className="qa-icon"><ExternalLink size={20} /></div>
              <div className="qa-title">Lakebase Docs</div>
              <div className="qa-desc">Official Databricks Lakebase documentation</div>
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
