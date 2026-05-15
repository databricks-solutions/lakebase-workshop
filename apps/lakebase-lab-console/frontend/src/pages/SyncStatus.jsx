import { useState, useEffect } from 'react'
import { api } from '../api'
import {
  RefreshCw, Database, ExternalLink, ChevronRight,
  Clock, Activity, AlertCircle, Play, Table, Layers
} from '../icons'
import LabBanner from '../LabBanner'

export default function SyncStatus({ config }) {
  const [syncedTables, setSyncedTables] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [triggeringId, setTriggeringId] = useState(null)
  const [triggerResult, setTriggerResult] = useState(null)

  const loadSyncedTables = async () => {
    setLoading(true)
    setError(null)
    try {
      const tables = await api.listSyncedTables()
      setSyncedTables(tables)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadSyncedTables() }, [])

  const triggerSync = async (tableId, pipelineId) => {
    setTriggeringId(tableId)
    setTriggerResult(null)
    try {
      const res = await api.triggerSync(encodeURIComponent(tableId), pipelineId)
      setTriggerResult({ tableId, success: true, message: res.message || 'Sync triggered' })
      setTimeout(loadSyncedTables, 3000)
    } catch (e) {
      setTriggerResult({ tableId, success: false, message: e.message })
    }
    setTriggeringId(null)
  }

  const stateColor = (state) => {
    if (!state) return 'badge-info'
    const s = state.toLowerCase()
    if (s.includes('active') || s.includes('online') || s.includes('ready') || s.includes('succeeded')) return 'badge-success'
    if (s.includes('provisioning') || s.includes('creating') || s.includes('updating') || s.includes('running')) return 'badge-warning'
    if (s.includes('failed') || s.includes('error')) return 'badge-danger'
    return 'badge-info'
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Reverse ETL & Data Sync</h2>
            <p>
              Bidirectional data sync between Unity Catalog and Lakebase. Push Delta tables
              into Lakebase for OLTP access, or sync Lakebase data back to the Lakehouse for analytics.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadSyncedTables} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="sync" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* ── Synced Tables List ── */}
      <div className="card">
        <div className="card-header">
          <h3><RefreshCw size={16} /> Synced Tables (Reverse ETL)</h3>
        </div>
        {loading ? (
          <div className="empty-state" style={{ padding: 20 }}><p>Loading synced tables...</p></div>
        ) : syncedTables.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><RefreshCw size={36} /></div>
            <p>No synced tables found. Create one using the Reverse ETL lab notebook at <code style={{ color: 'var(--accent)' }}>labs/reverse-etl/</code>.</p>
            <div className="code-block" style={{ marginTop: 16, textAlign: 'left', maxWidth: 600, margin: '16px auto' }}>{`from databricks.sdk.service.postgres import (
    SyncedTable, SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
    NewPipelineSpec,
)

w = WorkspaceClient()
w.postgres.create_synced_table(
    synced_table=SyncedTable(
        spec=SyncedTableSyncedTableSpec(
            branch="projects/<project_id>/branches/production",
            postgres_database="databricks_postgres",
            source_table_full_name="<catalog>.<schema>.<table>",
            primary_key_columns=["id"],
            scheduling_policy=SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.TRIGGERED,
            new_pipeline_spec=NewPipelineSpec(
                storage_catalog="<catalog>",
                storage_schema="<schema>",
            ),
        ),
    ),
    synced_table_id="<catalog>.<schema>.<table>_synced",
)`}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {triggerResult && (
              <div className={`info-box ${triggerResult.success ? 'info' : 'danger'}`}>
                <span style={{ fontWeight: 600 }}>{triggerResult.success ? 'Sync Triggered:' : 'Error:'}</span>
                <span>{triggerResult.message}</span>
              </div>
            )}
            {syncedTables.map((t, i) => (
              <div key={i} className="list-item-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span className="td-mono-bold" style={{ fontSize: 14 }}>{t.table_id || t.name}</span>
                  <div className="btn-row">
                    {t.state && <span className={`badge ${stateColor(t.state)}`}>{t.state}</span>}
                    <span className="badge badge-info">{t.branch_id}</span>
                    {t.pipeline_id && (
                      <button
                        className="btn btn-sm btn-secondary"
                        style={{ padding: '2px 8px', fontSize: 11 }}
                        onClick={() => triggerSync(t.table_id || t.name, t.pipeline_id)}
                        disabled={triggeringId === (t.table_id || t.name)}
                      >
                        <Play size={10} />
                        {triggeringId === (t.table_id || t.name) ? 'Triggering...' : 'Trigger Sync'}
                      </button>
                    )}
                  </div>
                </div>
                {t.source_table && (
                  <div className="td-mono-sm" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', marginBottom: 6 }}>
                    <Database size={12} /> Source: <code style={{ color: 'var(--accent)' }}>{t.source_table}</code>
                  </div>
                )}
                {t.primary_key_columns && t.primary_key_columns.length > 0 && (
                  <div className="td-mono-sm" style={{ color: 'var(--text-muted)' }}>
                    PK: {t.primary_key_columns.map(k => <span key={k} className="badge badge-cyan" style={{ marginRight: 4, fontSize: 10 }}>{k}</span>)}
                  </div>
                )}
                {t.scheduling_policy && (
                  <div className="td-mono-sm" style={{ color: 'var(--text-muted)', marginTop: 4 }}>
                    Schedule: <span className="badge badge-purple" style={{ fontSize: 10 }}>{t.scheduling_policy}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── How Reverse ETL Works ── */}
      <div className="card">
        <div className="card-header">
          <h3><Layers size={16} /> How Reverse ETL Works</h3>
        </div>
        <div className="flow-diagram flow-5">
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--blue)' }} /></div>
            <div className="flow-box-title">Delta Table</div>
            <div className="flow-box-subtitle">Unity Catalog</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Activity size={28} style={{ color: 'var(--teal)' }} /></div>
            <div className="flow-box-title">Sync Pipeline</div>
            <div className="flow-box-subtitle">Lakeflow</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--accent)' }} /></div>
            <div className="flow-box-title">PostgreSQL Table</div>
            <div className="flow-box-subtitle">Lakebase</div>
          </div>
        </div>
        <table className="data-table" style={{ marginTop: 16 }}>
          <thead>
            <tr><th>Sync Mode</th><th>Description</th><th>Latency</th><th>Best For</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><span className="badge badge-info">Snapshot</span></td>
              <td>One-time full copy</td>
              <td><span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Clock size={12} /> Minutes</span></td>
              <td>Initial setup, historical data</td>
            </tr>
            <tr>
              <td><span className="badge badge-warning">Triggered</span></td>
              <td>Incremental on-demand updates via CDF</td>
              <td><span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Clock size={12} /> Minutes</span></td>
              <td>Hourly/daily refreshes</td>
            </tr>
            <tr>
              <td><span className="badge badge-success">Continuous</span></td>
              <td>Real-time streaming sync</td>
              <td><span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Activity size={12} /> Seconds</span></td>
              <td>Live applications</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ── Forward ETL / Lakehouse Sync ── */}
      <div className="card">
        <div className="card-header">
          <h3><Table size={16} /> Forward ETL (Lakehouse Sync)</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16, lineHeight: 1.6 }}>
          Lakehouse Sync works in the opposite direction: data written to Lakebase PostgreSQL tables
          is automatically synced back to Unity Catalog as Delta tables. This enables operational data
          captured by OLTP applications to flow back into the Lakehouse for analytics, ML training, and reporting.
        </p>
        <div className="flow-diagram flow-5">
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--accent)' }} /></div>
            <div className="flow-box-title">PostgreSQL Table</div>
            <div className="flow-box-subtitle">Lakebase</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Activity size={28} style={{ color: 'var(--teal)' }} /></div>
            <div className="flow-box-title">Lakehouse Sync</div>
            <div className="flow-box-subtitle">Automatic</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--blue)' }} /></div>
            <div className="flow-box-title">Delta Table</div>
            <div className="flow-box-subtitle">Unity Catalog</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Automatic:</span>
            <span>Lakebase tables are automatically available as read-only Delta tables in Unity Catalog via the project's managed catalog.</span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Use Cases:</span>
            <span>Run Spark analytics on operational data, train ML models on live application data, build dashboards from OLTP tables, join transactional and analytical datasets.</span>
          </div>
          <div className="info-box warning">
            <span style={{ fontWeight: 600 }}>Latency:</span>
            <span>Forward sync has near real-time latency. Changes in Lakebase tables are typically reflected in the Delta tables within seconds to minutes.</span>
          </div>
        </div>
      </div>

      {/* ── Important Notes ── */}
      <div className="card">
        <div className="card-header">
          <h3>Important Notes</h3>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="info-box warning">
            <span style={{ fontWeight: 600 }}>CDF Required:</span>
            <span>Enable Change Data Feed on the source Delta table for Triggered/Continuous sync: <code>ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)</code></span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>SP Permissions:</span>
            <span>After sync completes, re-grant the App's Service Principal access to the new synced table. Synced tables are owned by the sync pipeline.</span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Connection Limits:</span>
            <span>Each synced table uses up to 16 connections. Plan your compute sizing accordingly.</span>
          </div>
          <div className="info-box danger">
            <span style={{ fontWeight: 600 }}>Size Limits:</span>
            <span>16 TB total across all synced tables per project.</span>
          </div>
        </div>
      </div>

      {/* ── Quick Links ── */}
      <div className="card">
        <div className="card-header">
          <h3>Quick Links</h3>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <a
            href={config?.workspace_host && config?.project_id
              ? `${config.workspace_host}/lakebase/projects/${config.project_id}${config.branch_id ? `?branchId=${config.branch_id}` : ''}`
              : undefined}
            className="btn btn-secondary"
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => { if (!config?.workspace_host || !config?.project_id) e.preventDefault() }}
          >
            <ExternalLink size={14} /> Open Lakebase UI
          </a>
          <a
            href={config?.workspace_host ? `${config.workspace_host}/explore/data` : undefined}
            className="btn btn-secondary"
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => { if (!config?.workspace_host) e.preventDefault() }}
          >
            <ExternalLink size={14} /> Open Catalog Explorer
          </a>
        </div>
      </div>
    </div>
  )
}
