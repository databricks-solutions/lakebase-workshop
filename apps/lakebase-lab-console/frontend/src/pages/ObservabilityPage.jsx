import { useState, useEffect } from 'react'
import { api } from '../api'
import { Activity, Database, Server, RefreshCw, Table, Cpu, Clock, AlertCircle } from '../icons'
import LabBanner from '../LabBanner'

export default function ObservabilityPage() {
  const [tab, setTab] = useState('overview')
  const [dbStats, setDbStats] = useState(null)
  const [tables, setTables] = useState([])
  const [indexes, setIndexes] = useState([])
  const [sizes, setSizes] = useState([])
  const [connections, setConnections] = useState(null)
  const [activity, setActivity] = useState([])
  const [statements, setStatements] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadAll = async () => {
    setLoading(true)
    setError(null)
    try {
      const [db, tbl, idx, sz, conn] = await Promise.allSettled([
        api.obsDatabaseStats(),
        api.obsTableStats(),
        api.obsIndexStats(),
        api.obsTableSizes(),
        api.obsConnections(),
      ])
      if (db.status === 'fulfilled') setDbStats(db.value)
      if (tbl.status === 'fulfilled') setTables(tbl.value)
      if (idx.status === 'fulfilled') setIndexes(idx.value)
      if (sz.status === 'fulfilled') setSizes(sz.value)
      if (conn.status === 'fulfilled') setConnections(conn.value)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  const loadActivity = async () => {
    try {
      const [act, stmts] = await Promise.allSettled([
        api.obsActivity(),
        api.obsStatements(),
      ])
      if (act.status === 'fulfilled') setActivity(act.value)
      if (stmts.status === 'fulfilled') setStatements(stmts.value)
    } catch {}
  }

  useEffect(() => { loadAll() }, [])

  const fmtNum = (n) => n != null ? Number(n).toLocaleString() : '--'

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Observability & Monitoring</h2>
            <p>
              Live PostgreSQL diagnostics from pg_stat views. Monitor database health,
              table activity, index usage, storage sizes, and active queries.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadAll} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="observability" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* Database Overview Metrics */}
      {dbStats && (
        <div className="metrics-row metrics-row-4">
          <div className="metric-card">
            <div className="metric-icon"><Server size={18} /></div>
            <div className="metric-value" style={{ color: 'var(--accent)' }}>{dbStats.cache_hit_ratio}%</div>
            <div className="metric-label">Cache Hit Ratio</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><Activity size={18} /></div>
            <div className="metric-value">{fmtNum(dbStats.active_connections)}</div>
            <div className="metric-label">Active Connections</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><Database size={18} /></div>
            <div className="metric-value">{fmtNum(dbStats.commits)}</div>
            <div className="metric-label">Commits</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon"><AlertCircle size={18} /></div>
            <div className="metric-value" style={{ color: (dbStats.deadlocks || 0) > 0 ? 'var(--danger)' : 'var(--success)' }}>
              {fmtNum(dbStats.deadlocks)}
            </div>
            <div className="metric-label">Deadlocks</div>
          </div>
        </div>
      )}

      <div className="tab-group">
        <button className={`tab-btn ${tab === 'overview' ? 'active' : ''}`} onClick={() => setTab('overview')}>
          Database Stats
        </button>
        <button className={`tab-btn ${tab === 'tables' ? 'active' : ''}`} onClick={() => setTab('tables')}>
          Table Activity
        </button>
        <button className={`tab-btn ${tab === 'indexes' ? 'active' : ''}`} onClick={() => setTab('indexes')}>
          Index Usage
        </button>
        <button className={`tab-btn ${tab === 'sizes' ? 'active' : ''}`} onClick={() => setTab('sizes')}>
          Storage Sizes
        </button>
        <button className={`tab-btn ${tab === 'activity' ? 'active' : ''}`} onClick={() => { setTab('activity'); loadActivity() }}>
          Active Queries
        </button>
        <button className={`tab-btn ${tab === 'statements' ? 'active' : ''}`} onClick={() => { setTab('statements'); loadActivity() }}>
          Top Queries
        </button>
      </div>

      {/* ── Database Stats ── */}
      {tab === 'overview' && dbStats && (
        <div className="grid-2col">
          <div className="card">
            <div className="card-header">
              <h3><Database size={16} /> Read/Write Activity</h3>
            </div>
            <div className="detail-row"><span className="detail-label">Rows Returned</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.rows_returned)}</span></div>
            <div className="detail-row"><span className="detail-label">Rows Fetched</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.rows_fetched)}</span></div>
            <div className="detail-row"><span className="detail-label">Rows Inserted</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.rows_inserted)}</span></div>
            <div className="detail-row"><span className="detail-label">Rows Updated</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.rows_updated)}</span></div>
            <div className="detail-row"><span className="detail-label">Rows Deleted</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.rows_deleted)}</span></div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3><Server size={16} /> Cache & Transactions</h3>
            </div>
            <div className="detail-row"><span className="detail-label">Cache Hits</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.cache_hits)}</span></div>
            <div className="detail-row"><span className="detail-label">Disk Reads</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.disk_reads)}</span></div>
            <div className="detail-row"><span className="detail-label">Cache Hit Ratio</span><span className="detail-value detail-value-mono" style={{ color: 'var(--accent)' }}>{dbStats.cache_hit_ratio}%</span></div>
            <div className="detail-row"><span className="detail-label">Commits</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.commits)}</span></div>
            <div className="detail-row"><span className="detail-label">Rollbacks</span><span className="detail-value detail-value-mono" style={{ color: (dbStats.rollbacks || 0) > 0 ? 'var(--warning)' : 'inherit' }}>{fmtNum(dbStats.rollbacks)}</span></div>
            <div className="detail-row"><span className="detail-label">Temp Files</span><span className="detail-value detail-value-mono">{fmtNum(dbStats.temp_files)}</span></div>
          </div>

          {connections && (
            <div className="card" style={{ gridColumn: 'span 2' }}>
              <div className="card-header">
                <h3><Cpu size={16} /> Connection Pool</h3>
              </div>
              <div className="metrics-row metrics-row-5">
                <div className="metric-card">
                  <div className="metric-value">{connections.total_connections}</div>
                  <div className="metric-label">Total</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value" style={{ color: 'var(--success)' }}>{connections.active}</div>
                  <div className="metric-label">Active</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value" style={{ color: 'var(--blue)' }}>{connections.idle}</div>
                  <div className="metric-label">Idle</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value" style={{ color: 'var(--warning)' }}>{connections.idle_in_transaction}</div>
                  <div className="metric-label">Idle in Txn</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value">{connections.max_connections}</div>
                  <div className="metric-label">Max Allowed</div>
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <div className="cu-gauge-labels" style={{ marginBottom: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                  <span>Connection Utilization</span>
                  <span className="td-mono">{connections.total_connections} / {connections.max_connections}</span>
                </div>
                <div className="cu-gauge">
                  <div className="cu-gauge-fill" style={{ width: `${connections.max_connections > 0 ? (connections.total_connections / connections.max_connections) * 100 : 0}%` }} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Table Activity ── */}
      {tab === 'tables' && (
        <div className="card">
          <div className="card-header">
            <h3><Table size={16} /> Table Activity (pg_stat_user_tables)</h3>
            <span className="badge badge-info">{tables.length} tables</span>
          </div>
          {tables.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No table stats available</p></div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Table</th><th>Seq Scans</th><th>Idx Scans</th>
                    <th>Live Rows</th><th>Dead Rows</th>
                    <th>Inserts</th><th>Updates</th><th>Deletes</th>
                    <th>Last Vacuum</th>
                  </tr>
                </thead>
                <tbody>
                  {tables.map((t, i) => (
                    <tr key={i}>
                      <td className="td-mono-bold">{t.table_name}</td>
                      <td className="td-mono">{fmtNum(t.seq_scan)}</td>
                      <td className="td-mono">{fmtNum(t.idx_scan)}</td>
                      <td className="td-mono">{fmtNum(t.live_rows)}</td>
                      <td className="td-mono" style={{ color: (t.dead_rows || 0) > 100 ? 'var(--warning)' : 'inherit' }}>{fmtNum(t.dead_rows)}</td>
                      <td className="td-mono">{fmtNum(t.inserts)}</td>
                      <td className="td-mono">{fmtNum(t.updates)}</td>
                      <td className="td-mono">{fmtNum(t.deletes)}</td>
                      <td className="td-mono-xs" style={{ color: 'var(--text-muted)' }}>{t.last_autovacuum || t.last_vacuum || '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Index Usage ── */}
      {tab === 'indexes' && (
        <div className="card">
          <div className="card-header">
            <h3><Database size={16} /> Index Usage (pg_stat_user_indexes)</h3>
            <span className="badge badge-info">{indexes.length} indexes</span>
          </div>
          {indexes.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No index stats available</p></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Table</th><th>Index</th><th>Scans</th><th>Tuples Read</th><th>Tuples Fetched</th></tr>
              </thead>
              <tbody>
                {indexes.map((idx, i) => (
                  <tr key={i}>
                    <td className="td-mono">{idx.table_name}</td>
                    <td className="td-mono-bold">{idx.index_name}</td>
                    <td className="td-mono">
                      <span className={`badge ${(idx.scans || 0) > 0 ? 'badge-success' : 'badge-warning'}`}>{fmtNum(idx.scans)}</span>
                    </td>
                    <td className="td-mono">{fmtNum(idx.tuples_read)}</td>
                    <td className="td-mono">{fmtNum(idx.tuples_fetched)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Storage Sizes ── */}
      {tab === 'sizes' && (
        <div className="card">
          <div className="card-header">
            <h3><Server size={16} /> Storage Sizes</h3>
          </div>
          {sizes.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No size data available</p></div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr><th>Table</th><th>Total Size</th><th>Table Data</th><th>Indexes</th></tr>
                </thead>
                <tbody>
                  {sizes.map((s, i) => (
                    <tr key={i}>
                      <td className="td-mono-bold">{s.table_name}</td>
                      <td className="td-mono" style={{ color: 'var(--accent)' }}>{s.total_size}</td>
                      <td className="td-mono">{s.table_size}</td>
                      <td className="td-mono">{s.index_size}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sizes.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="section-subheader">
                    Relative Table Sizes
                  </div>
                  {(() => {
                    const maxBytes = Math.max(...sizes.map(s => s.total_bytes || 0), 1)
                    return sizes.map((s, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                        <span style={{ width: 120, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{s.table_name}</span>
                        <div style={{ flex: 1, height: 14, background: 'var(--bg-inset)', borderRadius: 4, overflow: 'hidden', border: '1px solid var(--border)' }}>
                          <div style={{ height: '100%', width: `${((s.total_bytes || 0) / maxBytes) * 100}%`, background: 'linear-gradient(90deg, var(--accent), #2dd4bf)', borderRadius: 4, transition: 'width 0.3s' }} />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', minWidth: 70, textAlign: 'right' }}>{s.total_size}</span>
                      </div>
                    ))
                  })()}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Active Queries ── */}
      {tab === 'activity' && (
        <div className="card">
          <div className="card-header">
            <h3><Activity size={16} /> Active Queries (pg_stat_activity)</h3>
            <button className="btn btn-secondary btn-sm btn-icon" onClick={loadActivity}><RefreshCw size={14} /></button>
          </div>
          {activity.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No active queries at this moment</p></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {activity.map((a, i) => (
                <div key={i} className="list-item-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="badge badge-info">PID {a.pid}</span>
                      <span className={`badge ${a.state === 'active' ? 'badge-success' : a.state === 'idle' ? 'badge-cyan' : 'badge-warning'}`}>{a.state}</span>
                      {a.wait_event_type && <span className="badge badge-purple">{a.wait_event_type}: {a.wait_event}</span>}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{a.username}</span>
                  </div>
                  {a.query && (
                    <div className="code-block" style={{ fontSize: 11, maxHeight: 80, overflow: 'auto' }}>{a.query}</div>
                  )}
                  {a.query_start && (
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>Started: {a.query_start}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Top Queries ── */}
      {tab === 'statements' && (
        <div className="card">
          <div className="card-header">
            <h3><Clock size={16} /> Top Queries by Total Time (pg_stat_statements)</h3>
            <button className="btn btn-secondary btn-sm btn-icon" onClick={loadActivity}><RefreshCw size={14} /></button>
          </div>
          {statements.length === 0 ? (
            <div className="empty-state" style={{ padding: 20 }}>
              <div className="empty-icon"><Clock size={36} /></div>
              <p>pg_stat_statements not available or no query data yet. Run some queries first.</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Query</th><th>Calls</th><th>Total (ms)</th><th>Avg (ms)</th><th>Max (ms)</th><th>Rows</th>
                  </tr>
                </thead>
                <tbody>
                  {statements.map((s, i) => (
                    <tr key={i}>
                      <td className="td-mono-xs" style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.query_preview}>
                        {s.query_preview}
                      </td>
                      <td className="td-mono">{fmtNum(s.calls)}</td>
                      <td className="td-mono" style={{ color: 'var(--accent)' }}>{fmtNum(s.total_time_ms)}</td>
                      <td className="td-mono">{s.avg_time_ms}</td>
                      <td className="td-mono" style={{ color: (s.max_time_ms || 0) > 1000 ? 'var(--warning)' : 'inherit' }}>{s.max_time_ms}</td>
                      <td className="td-mono">{fmtNum(s.rows)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
