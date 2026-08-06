import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api'
import {
  Sun, Flame, Zap, Sparkles, Activity, Server,
  Play, Square, Settings, Clock, AlertCircle, RefreshCw, X, Trash2,
  Database, Cpu, ArrowUpRight, Boxes, Search
} from '../icons'
import LabBanner from '../LabBanner'

function cleanState(raw) {
  if (!raw) return 'unknown'
  const dot = raw.lastIndexOf('.')
  return dot >= 0 ? raw.slice(dot + 1) : raw
}

function stateClass(state) {
  if (!state) return 'unknown'
  if (state.includes('ACTIVE')) return 'active'
  if (state.includes('SCALING') || state.includes('STARTING')) return 'scaling'
  if (state.includes('SUSPENDED') || state.includes('IDLE')) return 'suspended'
  return 'unknown'
}

function fmtRows(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

const PRESETS = [
  { label: 'Light', Icon: Sun, colorClass: 'light', concurrency: 10, duration_seconds: 60, write_ratio: 0.3, write_batch_size: 500, desc: '500 rows/insert · 60s' },
  { label: 'Medium', Icon: Flame, colorClass: 'medium', concurrency: 20, duration_seconds: 120, write_ratio: 0.3, write_batch_size: 2000, desc: '2K rows/insert · 2 min' },
  { label: 'Heavy', Icon: Zap, colorClass: 'heavy', concurrency: 30, duration_seconds: 180, write_ratio: 0.4, write_batch_size: 5000, desc: '5K rows/insert · 3 min' },
  { label: 'Extreme', Icon: Sparkles, colorClass: 'extreme', concurrency: 50, duration_seconds: 300, write_ratio: 0.5, write_batch_size: 5000, desc: '5K rows/insert · 5 min' },
]

export default function AutoscaleDemo() {
  const [form, setForm] = useState({ concurrency: 10, duration_seconds: 60, write_ratio: 0.4, write_batch_size: 500 })
  const [testId, setTestId] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [computeHistory, setComputeHistory] = useState([])
  const [endpoints, setEndpoints] = useState([])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const [showCustom, setShowCustom] = useState(false)
  const pollRef = useRef(null)
  const computePollRef = useRef(null)
  const isRunning = metrics?.running === true

  const loadCompute = useCallback(async () => {
    try {
      const eps = await api.listEndpoints('production')
      setEndpoints(eps)
      return eps
    } catch { return [] }
  }, [])

  useEffect(() => { loadCompute() }, [loadCompute])

  useEffect(() => {
    api.activeLoadTest()
      .then((s) => {
        setTestId(s.test_id)
        setMetrics(s)
      })
      .catch(() => {})
  }, [])

  const startTest = async (preset) => {
    const config = preset || form
    setStarting(true)
    setError(null)
    setHistory([])
    setComputeHistory([])
    try {
      const res = await api.startLoadTest(config)
      setTestId(res.test_id)
      setMetrics(res)
    } catch (e) {
      setError(e.message)
    }
    setStarting(false)
  }

  const stopTest = async () => {
    if (testId) {
      try { await api.stopLoadTest(testId) } catch {}
    }
  }

  useEffect(() => {
    if (!testId) return

    pollRef.current = setInterval(async () => {
      try {
        const s = await api.loadTestStatus(testId)
        setMetrics(s)
        setHistory((h) => [...h.slice(-89), {
          t: Math.round(s.elapsed_seconds),
          qps: s.qps,
          avg: s.avg_latency_ms,
          p95: s.p95_latency_ms,
          errors: s.total_errors,
          reads: s.read_queries,
          writes: s.write_queries,
          rowsWritten: s.rows_written,
          rowsRead: s.rows_read,
        }])
        if (!s.running) clearInterval(pollRef.current)
      } catch {}
    }, 1000)

    computePollRef.current = setInterval(async () => {
      try {
        const eps = await api.listEndpoints('production')
        setEndpoints(eps)
        const ep = eps[0]
        if (ep) {
          setComputeHistory((h) => [...h.slice(-59), {
            t: Date.now(),
            state: cleanState(ep.state),
            rawState: ep.state,
            min_cu: ep.min_cu,
            max_cu: ep.max_cu,
            connections: ep.db_active_connections || 0,
            cache_hit_ratio: ep.db_cache_hit_ratio || 0,
            transactions: ep.db_total_transactions || 0,
          }])
        }
      } catch {}
    }, 3000)

    return () => {
      clearInterval(pollRef.current)
      clearInterval(computePollRef.current)
    }
  }, [testId])

  const ep = endpoints[0] || {}
  const maxQps = Math.max(...history.map((h) => h.qps), 1)
  const maxLat = Math.max(...history.map((h) => h.p95), 1)
  const barHeight = history.length > 60 ? 6 : history.length > 30 ? 10 : 16
  const activePreset = metrics ? PRESETS.find(p => p.concurrency === metrics.concurrency) : null

  return (
    <div>
      <div className="page-header">
        <h2>Autoscale Demo</h2>
        <p>
          Send traffic spikes to Lakebase and watch it respond in real time through endpoint
          state changes, connection counts, and latency. The autoscaler adjusts CU between your
          configured min and max based on demand — see the exact live CU in the Lakebase Metrics dashboard.
        </p>
      </div>
      <LabBanner pageId="autoscale" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
          <button className="btn btn-sm btn-secondary" onClick={() => setError(null)}>
            <X size={14} /> Dismiss
          </button>
        </div>
      )}

      {/* Compute Status */}
      <div className="card">
        <div className="card-header">
          <h3><Server size={16} /> Compute Status</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`badge ${ep.state?.includes('ACTIVE') ? 'badge-success' : 'badge-warning'}`}>
              {cleanState(ep.state)}
            </span>
            {isRunning && <span className="badge badge-accent" style={{ animation: 'pulse 2s infinite' }}>MONITORING</span>}
          </div>
        </div>
        <div className="metrics-row metrics-row-4" style={{ marginBottom: 8 }}>
          <div className="metric-card">
            <div className="metric-value">{ep.min_cu ?? '--'}</div>
            <div className="metric-label">Min CU</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{ep.max_cu ?? '--'}</div>
            <div className="metric-label">Max CU</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{ep.min_cu != null ? `${(ep.min_cu * 2).toFixed(0)}-${(ep.max_cu * 2).toFixed(0)}` : '--'}</div>
            <div className="metric-label">RAM (GB)</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{ep.endpoint_type?.replace(/^.*\./, '') || '--'}</div>
            <div className="metric-label">Type</div>
          </div>
        </div>

        {ep.min_cu != null && (
          <div style={{ padding: '0 4px' }}>
            <div className="cu-gauge">
              <div className="cu-gauge-fill" style={{ width: `${((ep.max_cu || 0) / 112) * 100}%` }} />
            </div>
            <div className="cu-gauge-labels">
              <span>0 CU</span>
              <span>{ep.min_cu}-{ep.max_cu} CU configured</span>
              <span>112 CU max</span>
            </div>
          </div>
        )}
      </div>

      {/* Spike Controls */}
      <div className="card">
        <div className="card-header">
          <h3>
            {isRunning ? (
              <><Activity size={16} /> Spike In Progress</>
            ) : (
              <><Play size={16} /> Send a Traffic Spike</>
            )}
          </h3>
          {isRunning && (
            <button className="btn btn-danger btn-sm" onClick={stopTest}>
              <Square size={14} /> Stop
            </button>
          )}
        </div>

        {!isRunning && (
          <>
            <div className="spike-presets">
              {PRESETS.map((p) => (
                <button
                  key={p.label}
                  className="spike-preset-btn"
                  onClick={() => startTest(p)}
                  disabled={starting}
                >
                  <span className={`spike-preset-icon ${p.colorClass}`}><p.Icon size={22} /></span>
                  <span className="spike-preset-label">{p.label}</span>
                  <span className="spike-preset-desc">{p.desc}</span>
                  <span className="spike-preset-desc">
                    {p.concurrency} workers &middot; {Math.round(p.write_ratio * 100)}% writes
                  </span>
                </button>
              ))}
            </div>

            <div style={{ marginTop: 14 }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setShowCustom(!showCustom)}
              >
                <Settings size={14} />
                {showCustom ? 'Hide' : 'Show'} Custom Config
              </button>
            </div>

            {showCustom && (
              <div className="form-inset" style={{ marginTop: 14 }}>
                <div className="form-row">
                  <div className="form-group">
                    <label>Concurrent Workers</label>
                    <input
                      type="number" min={1} max={100}
                      value={form.concurrency}
                      onChange={(e) => setForm({ ...form, concurrency: parseInt(e.target.value) || 10 })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Duration (seconds)</label>
                    <input
                      type="number" min={5} max={600}
                      value={form.duration_seconds}
                      onChange={(e) => setForm({ ...form, duration_seconds: parseInt(e.target.value) || 60 })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Rows per INSERT</label>
                    <input
                      type="number" min={1} max={10000}
                      value={form.write_batch_size}
                      onChange={(e) => setForm({ ...form, write_batch_size: parseInt(e.target.value) || 500 })}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Write Ratio ({Math.round(form.write_ratio * 100)}% writes / {Math.round((1 - form.write_ratio) * 100)}% reads)</label>
                  <input
                    type="range" min={0} max={1} step={0.1}
                    value={form.write_ratio}
                    onChange={(e) => setForm({ ...form, write_ratio: parseFloat(e.target.value) })}
                  />
                </div>
                <button className="btn btn-primary" onClick={() => startTest()} disabled={starting}>
                  <Play size={14} />
                  {starting ? 'Starting...' : 'Start Custom Spike'}
                </button>
              </div>
            )}
          </>
        )}

        {/* Active test config summary */}
        {isRunning && metrics && (
          <div className="running-config">
            <span className="text-muted">
              <strong>{metrics.concurrency}</strong> workers
            </span>
            <span className="text-muted">
              <strong>{metrics.write_batch_size || 100}</strong> rows/insert
            </span>
            <span className="text-muted">
              <strong style={{ color: 'var(--accent)' }}>{Math.round((metrics.write_ratio || 0) * 100)}%</strong> writes
              {' / '}
              <strong style={{ color: 'var(--blue)' }}>{Math.round((1 - (metrics.write_ratio || 0)) * 100)}%</strong> reads
            </span>
            <span className="text-muted">
              Elapsed: <strong>{metrics.elapsed_seconds}s</strong>
            </span>
          </div>
        )}
      </div>

      {/* Live Metrics */}
      {metrics && (
        <>
          {/* Row throughput */}
          <div className="metrics-row metrics-row-4">
            <div className="metric-card">
              <div className="metric-value" style={{ color: 'var(--accent)' }}>
                {fmtRows(metrics.rows_written || 0)}
              </div>
              <div className="metric-label">Rows Written</div>
            </div>
            <div className="metric-card">
              <div className="metric-value" style={{ color: 'var(--blue)' }}>
                {fmtRows(metrics.rows_read || 0)}
              </div>
              <div className="metric-label">Rows Scanned</div>
            </div>
            <div className="metric-card">
              <div className="metric-value" style={{ color: isRunning ? 'var(--accent)' : 'var(--text-secondary)' }}>
                {metrics.qps}
              </div>
              <div className="metric-label">Queries/sec</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.total_queries.toLocaleString()}</div>
              <div className="metric-label">Total Queries</div>
            </div>
          </div>

          {/* Latency + health */}
          <div className="metrics-row metrics-row-4">
            <div className="metric-card">
              <div className="metric-value">{metrics.avg_latency_ms}</div>
              <div className="metric-label">Avg Latency (ms)</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{metrics.p95_latency_ms}</div>
              <div className="metric-label">P95 Latency (ms)</div>
            </div>
            <div className="metric-card">
              <div className="metric-value" style={{ color: metrics.total_errors > 0 ? 'var(--danger)' : 'var(--success)' }}>
                {metrics.total_errors}
              </div>
              <div className="metric-label">Errors</div>
            </div>
            <div className="metric-card">
              <div className="metric-value" style={{ color: 'var(--blue)' }}>
                {metrics.db_cache_hit_ratio ? `${metrics.db_cache_hit_ratio}%` : '--'}
              </div>
              <div className="metric-label">Cache Hit Ratio</div>
            </div>
          </div>

          {/* Read / Write Breakdown */}
          <div className="card">
            <div className="card-header">
              <h3><Database size={16} /> Query Breakdown</h3>
              <span className="badge badge-purple">{metrics.total_queries.toLocaleString()} total queries</span>
            </div>
            <div className="rw-breakdown">
              <div className="rw-section">
                <div className="rw-header">
                  <span className="rw-dot" style={{ background: 'var(--teal)' }} />
                  <span className="rw-title">Point Lookups</span>
                  <span className="badge badge-success" style={{ marginLeft: 'auto' }}>PK Index</span>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>
                  Single-row fetches by primary key (<code style={{ color: 'var(--teal)' }}>SELECT ... WHERE event_id = ?</code>) — the core OLTP read pattern. Should show low, stable latency regardless of table size.
                </p>
                <div className="rw-stats">
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--teal)' }}>{(metrics.lookup_queries || 0).toLocaleString()}</div>
                    <div className="rw-stat-label">Queries</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--teal)', fontSize: metrics.lookup_avg_latency_ms < 10 ? 28 : undefined, fontWeight: metrics.lookup_avg_latency_ms < 10 ? 700 : undefined }}>{metrics.lookup_avg_latency_ms || 0}</div>
                    <div className="rw-stat-label">Avg Latency (ms)</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: metrics.lookup_avg_latency_ms > 0 && metrics.read_avg_latency_ms > 0 ? 'var(--teal)' : 'var(--text-secondary)' }}>
                      {metrics.lookup_avg_latency_ms > 0 && metrics.read_avg_latency_ms > 0
                        ? `${Math.round(metrics.read_avg_latency_ms / metrics.lookup_avg_latency_ms)}x`
                        : '--'}
                    </div>
                    <div className="rw-stat-label">Faster than Scans</div>
                  </div>
                </div>
                <div className="rw-bar-track">
                  <div className="rw-bar-fill" style={{ background: 'var(--teal)', width: `${metrics.total_queries > 0 ? ((metrics.lookup_queries || 0) / metrics.total_queries * 100) : 0}%` }} />
                </div>
                {(metrics.lookup_errors || 0) > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>{metrics.lookup_errors} errors</div>
                )}
              </div>

              <div className="rw-section">
                <div className="rw-header">
                  <span className="rw-dot read" />
                  <span className="rw-title">Scan Reads</span>
                  <span className="badge badge-info" style={{ marginLeft: 'auto' }}>Aggregations</span>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>
                  Analytical queries: aggregations, window functions, and full-table scans on <code style={{ color: 'var(--blue)' }}>events</code> to push CPU and trigger autoscaling
                </p>
                <div className="rw-stats">
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--blue)' }}>{(metrics.read_queries || 0).toLocaleString()}</div>
                    <div className="rw-stat-label">Queries</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--blue)' }}>{fmtRows(metrics.rows_read || 0)}</div>
                    <div className="rw-stat-label">Rows Scanned</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--blue)' }}>{metrics.read_avg_latency_ms || 0}</div>
                    <div className="rw-stat-label">Avg Latency (ms)</div>
                  </div>
                </div>
                <div className="rw-bar-track">
                  <div className="rw-bar-fill read" style={{ width: `${metrics.total_queries > 0 ? ((metrics.read_queries || 0) / metrics.total_queries * 100) : 0}%` }} />
                </div>
                {(metrics.read_errors || 0) > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>{metrics.read_errors} errors</div>
                )}
              </div>

              <div className="rw-section">
                <div className="rw-header">
                  <span className="rw-dot write" />
                  <span className="rw-title">Writes</span>
                  <span className="badge badge-accent" style={{ marginLeft: 'auto' }}>Batch INSERT</span>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>
                  Batch inserts of {metrics.write_batch_size || 100} rows via <code style={{ color: 'var(--accent)' }}>generate_series</code> into <code style={{ color: 'var(--accent)' }}>events</code> (each row also fires the audit trigger)
                </p>
                <div className="rw-stats">
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--accent)' }}>{(metrics.write_queries || 0).toLocaleString()}</div>
                    <div className="rw-stat-label">Queries</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--accent)' }}>{fmtRows(metrics.rows_written || 0)}</div>
                    <div className="rw-stat-label">Rows Written</div>
                  </div>
                  <div>
                    <div className="rw-stat-value" style={{ color: 'var(--accent)' }}>{metrics.write_avg_latency_ms || 0}</div>
                    <div className="rw-stat-label">Avg Latency (ms)</div>
                  </div>
                </div>
                <div className="rw-bar-track">
                  <div className="rw-bar-fill write" style={{ width: `${metrics.total_queries > 0 ? ((metrics.write_queries || 0) / metrics.total_queries * 100) : 0}%` }} />
                </div>
                {(metrics.write_errors || 0) > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>{metrics.write_errors} errors</div>
                )}
              </div>
            </div>
          </div>

          {/* QPS + Latency Charts */}
          <div className="grid-2col">
            <div className="card">
              <div className="card-header">
                <h3><Activity size={16} /> Throughput (QPS)</h3>
                {history.length > 0 && (
                  <span className="badge badge-accent">
                    peak: {Math.max(...history.map(h => h.qps)).toFixed(1)}
                  </span>
                )}
              </div>
              <div className="chart-area" style={{ minHeight: 160 }}>
                {history.length === 0 ? (
                  <div className="empty-state empty-state-compact"><p>Waiting for data...</p></div>
                ) : (
                  history.map((h, i) => (
                    <div className="chart-bar-row" key={i} style={{ marginBottom: Math.max(1, 4 - Math.floor(history.length / 20)) }}>
                      <span className="chart-bar-label">{h.qps}</span>
                      <div className="chart-bar" style={{ width: `${(h.qps / maxQps) * 100}%`, height: barHeight }} />
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <h3><Clock size={16} /> P95 Latency (ms)</h3>
                {history.length > 0 && (
                  <span className="badge badge-info">
                    peak: {Math.max(...history.map(h => h.p95)).toFixed(0)}ms
                  </span>
                )}
              </div>
              <div className="chart-area" style={{ minHeight: 160 }}>
                {history.length === 0 ? (
                  <div className="empty-state empty-state-compact"><p>Waiting for data...</p></div>
                ) : (
                  history.map((h, i) => (
                    <div className="chart-bar-row" key={i} style={{ marginBottom: Math.max(1, 4 - Math.floor(history.length / 20)) }}>
                      <span className="chart-bar-label">{h.p95.toFixed(0)}</span>
                      <div className="chart-bar latency" style={{ width: `${(h.p95 / maxLat) * 100}%`, height: barHeight }} />
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Compute & DB Metrics Timeline */}
          {computeHistory.length > 0 && (() => {
            const maxConns = Math.max(...computeHistory.map(c => c.connections), 1)
            const firstTxn = computeHistory[0].transactions || 0
            const txnDeltas = computeHistory.map((c, i) => {
              if (i === 0) return 0
              const prev = computeHistory[i - 1].transactions || 0
              return Math.max(0, (c.transactions || 0) - prev)
            })
            const maxTxnDelta = Math.max(...txnDeltas, 1)
            return (
            <div className="card">
              <div className="card-header">
                <h3><Cpu size={16} /> Compute & DB Metrics</h3>
                <span className="badge badge-info">{computeHistory.length} samples &middot; every 3s</span>
              </div>

              {/* DB metrics summary */}
              <div className="metrics-row metrics-row-4" style={{ marginBottom: 16 }}>
                <div className="metric-card">
                  <div className="metric-value" style={{ color: 'var(--accent)' }}>
                    {computeHistory[computeHistory.length - 1].connections}
                  </div>
                  <div className="metric-label">Active Connections</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value" style={{ color: 'var(--blue)' }}>
                    {computeHistory[computeHistory.length - 1].cache_hit_ratio}%
                  </div>
                  <div className="metric-label">Cache Hit Ratio</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value">
                    {((computeHistory[computeHistory.length - 1].transactions || 0) - firstTxn).toLocaleString()}
                  </div>
                  <div className="metric-label">Transactions (delta)</div>
                </div>
                <div className="metric-card">
                  <div className="metric-value">
                    <span className={`badge ${ep.state?.includes('ACTIVE') ? 'badge-success' : ep.state?.includes('SCAL') ? 'badge-warning' : 'badge-info'}`}>
                      {cleanState(ep.state)}
                    </span>
                  </div>
                  <div className="metric-label">Endpoint State</div>
                </div>
              </div>

              {/* Connections chart */}
              <div style={{ marginBottom: 16 }}>
                <div className="section-subheader">
                  Active DB Connections Over Time
                </div>
                <div className="compute-timeline">
                  <div className="compute-timeline-chart">
                    {computeHistory.map((c, i) => {
                      const pct = (c.connections / maxConns) * 100
                      const cls = stateClass(c.rawState || c.state)
                      return (
                        <div key={i} className="ct-bar-group" title={`${new Date(c.t).toLocaleTimeString()} — ${c.connections} connections (${c.state}, ${c.min_cu}-${c.max_cu} CU)`}>
                          <div className={`ct-bar ${cls}`} style={{ height: `${Math.max(pct, 4)}%` }} />
                        </div>
                      )
                    })}
                  </div>
                  <div className="compute-timeline-axis">
                    <span>{new Date(computeHistory[0].t).toLocaleTimeString()}</span>
                    {computeHistory.length > 2 && (
                      <span>{new Date(computeHistory[Math.floor(computeHistory.length / 2)].t).toLocaleTimeString()}</span>
                    )}
                    <span>{new Date(computeHistory[computeHistory.length - 1].t).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>

              {/* Transactions/sec chart */}
              <div style={{ marginBottom: 16 }}>
                <div className="section-subheader">
                  Transactions per Interval (3s)
                </div>
                <div className="compute-timeline">
                  <div className="compute-timeline-chart">
                    {txnDeltas.map((delta, i) => {
                      const pct = (delta / maxTxnDelta) * 100
                      return (
                        <div key={i} className="ct-bar-group" title={`${new Date(computeHistory[i].t).toLocaleTimeString()} — ${delta.toLocaleString()} txn`}>
                          <div className="ct-bar active" style={{ height: `${Math.max(pct, 2)}%`, opacity: delta > 0 ? 1 : 0.2 }} />
                        </div>
                      )
                    })}
                  </div>
                  <div className="compute-timeline-axis">
                    <span>{new Date(computeHistory[0].t).toLocaleTimeString()}</span>
                    {computeHistory.length > 2 && (
                      <span>{new Date(computeHistory[Math.floor(computeHistory.length / 2)].t).toLocaleTimeString()}</span>
                    )}
                    <span>{new Date(computeHistory[computeHistory.length - 1].t).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>

              {/* State change log */}
              <div>
                <div className="section-subheader">
                  State Changes
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {computeHistory.filter((c, i) => i === 0 || c.state !== computeHistory[i-1].state).map((c, i) => (
                    <div key={i} className="compute-log-row">
                      <span className="compute-log-time">
                        {new Date(c.t).toLocaleTimeString()}
                      </span>
                      <span className={`badge ${c.state === 'ACTIVE' ? 'badge-success' : c.state?.includes('SCAL') ? 'badge-warning' : 'badge-info'}`}>
                        {c.state}
                      </span>
                      <span className="compute-log-cu">
                        {c.min_cu}-{c.max_cu} CU
                      </span>
                      {i > 0 && (
                        <span className="badge badge-accent" style={{ marginLeft: 'auto' }}>STATE CHANGE</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            )
          })()}

          {/* Actions */}
          <div className="btn-row" style={{ marginBottom: 16 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => api.clearLoadtestEvents()}>
              <Trash2 size={14} /> Clear Test Events
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => { setHistory([]); setComputeHistory([]); setMetrics(null); setTestId(null) }}>
              <RefreshCw size={14} /> Reset Charts
            </button>
          </div>
        </>
      )}

      {/* What Happens When You Send a Spike */}
      {!metrics && (
        <>
          <div className="card">
            <div className="card-header">
              <h3><Boxes size={16} /> What Happens When You Send a Spike</h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7, marginBottom: 16 }}>
              Each preset spawns concurrent async workers that fire a mix of <strong>point lookups</strong>, <strong>analytical scans</strong>, and <strong>batch writes</strong> using connection pooling.
              Point lookups show Lakebase's OLTP strength (low-ms PK reads), while scans and writes push CPU high enough to trigger autoscaling.
            </p>
            <div className="explainer-grid">
              <div className="explainer-item">
                <div className="explainer-icon" style={{ background: 'var(--teal-dim)', color: 'var(--teal)' }}>
                  <Search size={18} />
                </div>
                <div className="explainer-text">
                  <h4>Point Lookups (PK Index)</h4>
                  <p>Half of read workers do single-row <code>SELECT ... WHERE event_id = ?</code> fetches. These hit the primary key B-tree index and return in 1-5 ms regardless of table size — the core OLTP pattern.</p>
                </div>
              </div>
              <div className="explainer-item">
                <div className="explainer-icon" style={{ background: 'var(--blue-dim)', color: 'var(--blue)' }}>
                  <Database size={18} />
                </div>
                <div className="explainer-text">
                  <h4>Scan Reads (Analytical)</h4>
                  <p>The other half run aggregations, window functions, and bounded scans on <code>events</code> to push CPU. These are intentionally heavier to contrast with point lookup latency and trigger autoscaling.</p>
                </div>
              </div>
              <div className="explainer-item">
                <div className="explainer-icon" style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
                  <ArrowUpRight size={18} />
                </div>
                <div className="explainer-text">
                  <h4>Batch Writes (INSERT)</h4>
                  <p>Each write inserts 500-5,000 rows with ~500-byte JSONB payloads via <code>generate_series</code>. The audit trigger fires per row, doubling effective I/O. This rapidly grows the working set beyond available RAM.</p>
                </div>
              </div>
              <div className="explainer-item">
                <div className="explainer-icon" style={{ background: 'var(--purple-dim)', color: 'var(--purple)' }}>
                  <Cpu size={18} />
                </div>
                <div className="explainer-text">
                  <h4>Autoscaler Triggers</h4>
                  <p>Lakebase monitors <strong>CPU load</strong>, <strong>memory usage</strong>, and <strong>working set size</strong>. Watch how point lookup latency stays stable even as scans slow down — then both improve as the autoscaler adds compute.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>How Autoscaling Works</h3>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7, marginBottom: 20 }}>
              Lakebase autoscales compute between your configured <strong>min</strong> and <strong>max CU</strong> limits.
              When traffic increases, the autoscaler detects higher resource utilization and scales up compute
              to handle the load. When traffic subsides, compute scales back down. If there is zero activity,
              compute can scale to zero to minimize costs.
            </p>
            <div className="step-grid">
              <div className="step-card">
                <div className="step-number">1</div>
                <div className="step-title">Send Spike</div>
                <div className="step-desc">Workers begin firing batch inserts and heavy scan queries</div>
              </div>
              <div className="step-card">
                <div className="step-number">2</div>
                <div className="step-title">CPU Pressure Builds</div>
                <div className="step-desc">Full-table scans and batch writes drive utilization up</div>
              </div>
              <div className="step-card">
                <div className="step-number">3</div>
                <div className="step-title">Autoscaler Reacts</div>
                <div className="step-desc">The endpoint scales up CU to handle the increased load</div>
              </div>
              <div className="step-card">
                <div className="step-number">4</div>
                <div className="step-title">Latency Stabilizes</div>
                <div className="step-desc">As compute scales up, query times flatten out</div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
