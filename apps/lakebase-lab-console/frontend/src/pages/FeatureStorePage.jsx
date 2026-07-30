import { useState, useEffect } from 'react'
import { api } from '../api'
import { Database, RefreshCw, Table, Server, Activity, AlertCircle, ChevronRight, Layers } from '../icons'
import LabBanner from '../LabBanner'

export default function FeatureStorePage() {
  const [tab, setTab] = useState('stores')
  const [onlineStores, setOnlineStores] = useState([])
  const [featureSpecs, setFeatureSpecs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mineOnly, setMineOnly] = useState(true)

  const loadAll = async (filterMine) => {
    const showMine = filterMine !== undefined ? filterMine : mineOnly
    setLoading(true)
    setError(null)
    try {
      const [stores, features] = await Promise.allSettled([
        api.listOnlineStores(showMine),
        api.listFeatureSpecs(),
      ])
      if (stores.status === 'fulfilled') setOnlineStores(stores.value)
      if (features.status === 'fulfilled') setFeatureSpecs(features.value)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadAll() }, [])

  const toggleMineOnly = () => {
    const next = !mineOnly
    setMineOnly(next)
    loadAll(next)
  }

  const stateColor = (state) => {
    if (!state) return 'badge-info'
    const s = state.toLowerCase()
    if (s.includes('active') || s.includes('online') || s.includes('ready')) return 'badge-success'
    if (s.includes('provisioning') || s.includes('creating') || s.includes('updating')) return 'badge-warning'
    if (s.includes('failed') || s.includes('error')) return 'badge-danger'
    return 'badge-info'
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Feature Store</h2>
            <p>
              Real-time ML feature serving powered by your existing Lakebase project. Feature tables are
              published directly into your Lakebase instance for sub-millisecond lookups.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadAll} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="feature-store" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      <div className="metrics-row metrics-row-2">
        <div className="metric-card">
          <div className="metric-icon"><Server size={18} /></div>
          <div className="metric-value">{onlineStores.length}</div>
          <div className="metric-label">Online Stores</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Table size={18} /></div>
          <div className="metric-value">{featureSpecs.length}</div>
          <div className="metric-label">Feature Specs</div>
        </div>
      </div>

      <div className="tab-group">
        <button className={`tab-btn ${tab === 'stores' ? 'active' : ''}`} onClick={() => setTab('stores')}>
          Online Stores ({onlineStores.length})
        </button>
        <button className={`tab-btn ${tab === 'features' ? 'active' : ''}`} onClick={() => setTab('features')}>
          Feature Specs ({featureSpecs.length})
        </button>
        <button className={`tab-btn ${tab === 'guide' ? 'active' : ''}`} onClick={() => setTab('guide')}>
          How It Works
        </button>
      </div>

      {/* ── Online Stores ── */}
      {tab === 'stores' && (
        <div className="card">
          <div className="card-header">
            <h3><Server size={16} /> Lakebase Online Stores</h3>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={mineOnly}
                onChange={toggleMineOnly}
                style={{ cursor: 'pointer' }}
              />
              Show only mine
            </label>
          </div>
          {loading ? (
            <div className="empty-state empty-state-compact"><p>Loading...</p></div>
          ) : onlineStores.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Server size={36} /></div>
              <p>No online stores found. Run the Online Feature Store lab notebook at <code style={{ color: 'var(--accent)' }}>labs/online-feature-store/</code> to publish features to your existing Lakebase project.</p>
              <div className="code-block" style={{ marginTop: 16, textAlign: 'left', maxWidth: 600, margin: '16px auto' }}>{`from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()

# Reuse your existing Lakebase project as the online store
online_store = fe.get_online_store(name=PROJECT_ID)

# Publish features from an offline table
fe.publish_table(
    online_store=online_store,
    source_table_name="catalog.schema.customer_features",
    online_table_name="catalog.schema.customer_features_online",
)`}</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {onlineStores.map((s, i) => (
                <div key={i} className="list-item-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span className="td-mono-bold" style={{ fontSize: 14 }}>{s.store_id || s.name}</span>
                    <div className="btn-row">
                      {s.capacity && <span className="badge badge-purple" style={{ fontSize: 10 }}>{s.capacity}</span>}
                      {s.state && <span className={`badge ${stateColor(s.state)}`}>{s.state}</span>}
                    </div>
                  </div>
                  {s.read_write_dns && (
                    <div className="td-mono-sm" style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>
                      <Server size={12} style={{ verticalAlign: -2 }} /> <code style={{ color: 'var(--accent)', fontSize: 11 }}>{s.read_write_dns}</code>
                    </div>
                  )}
                  {s.source_table && (
                    <div className="td-mono-sm" style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>
                      <Database size={12} style={{ verticalAlign: -2 }} /> Source: <code style={{ color: 'var(--accent)' }}>{s.source_table}</code>
                    </div>
                  )}
                  {s.primary_key_columns && s.primary_key_columns.length > 0 && (
                    <div className="td-mono-sm" style={{ color: 'var(--text-muted)', marginTop: 4 }}>
                      PK: {s.primary_key_columns.map(k => <span key={k} className="badge badge-cyan" style={{ marginRight: 4, fontSize: 10 }}>{k}</span>)}
                    </div>
                  )}
                  {s.creator && (
                    <div className="td-mono-xs" style={{ color: 'var(--text-muted)', marginTop: 4 }}>Created by: {s.creator}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Feature Specs ── */}
      {tab === 'features' && (
        <div className="card">
          <div className="card-header">
            <h3><Table size={16} /> Unity Catalog Online Table Specs</h3>
          </div>
          {loading ? (
            <div className="empty-state empty-state-compact"><p>Loading...</p></div>
          ) : featureSpecs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Table size={36} /></div>
              <p>No online table feature specs found. These are created via the Feature Engineering client when you publish features to an online store.</p>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Name</th><th>Source Table</th><th>Primary Key</th><th>State</th><th>Mode</th></tr>
              </thead>
              <tbody>
                {featureSpecs.map((f, i) => (
                  <tr key={i}>
                    <td className="td-mono-bold">{f.name}</td>
                    <td className="td-mono-sm">{f.source_table || '--'}</td>
                    <td>{(f.primary_key_columns || []).map(k => <span key={k} className="badge badge-cyan" style={{ marginRight: 4, fontSize: 10 }}>{k}</span>)}</td>
                    <td><span className={`badge ${stateColor(f.state)}`}>{f.state || '--'}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {f.run_continuously ? 'Continuous' : f.run_triggered ? 'Triggered' : 'Snapshot'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── How It Works Guide ── */}
      {tab === 'guide' && (
        <>
          <div className="card">
            <div className="card-header">
              <h3><Layers size={16} /> Online Feature Store Architecture</h3>
            </div>
            <div className="flow-diagram flow-5">
              <div className="flow-box">
                <div style={{ marginBottom: 8 }}><Table size={28} style={{ color: 'var(--blue)' }} /></div>
                <div className="flow-box-title">Feature Table</div>
                <div className="flow-box-subtitle">Delta + CDF</div>
              </div>
              <div className="flow-arrow"><ChevronRight size={32} /></div>
              <div className="flow-box">
                <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--accent)' }} /></div>
                <div className="flow-box-title">Online Store</div>
                <div className="flow-box-subtitle">Lakebase-backed</div>
              </div>
              <div className="flow-arrow"><ChevronRight size={32} /></div>
              <div className="flow-box">
                <div style={{ marginBottom: 8 }}><Activity size={28} style={{ color: 'var(--success)' }} /></div>
                <div className="flow-box-title">Feature Serving</div>
                <div className="flow-box-subtitle">Low-latency lookups</div>
              </div>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7, marginTop: 12 }}>
              Online stores provide sub-millisecond feature lookups for ML models at inference time.
              Data is synced from Delta tables via the <code>publish_table</code> API. Lakebase provides
              the PostgreSQL-compatible serving layer with autoscaling compute.
            </p>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Key Concepts</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Online Store:</span>
                <span>Your existing Lakebase project, reused for feature serving. No separate instance needed — feature tables coexist with your workshop data.</span>
              </div>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Feature Spec:</span>
                <span>A Unity Catalog online table definition that tracks which offline feature table is published to which online store.</span>
              </div>
              <div className="info-box warning">
                <span style={{ fontWeight: 600 }}>Publish Modes:</span>
                <span><strong>Triggered</strong> (incremental on-demand), <strong>Continuous</strong> (streaming), or <strong>Snapshot</strong> (full copy). Requires Change Data Feed enabled on the source table.</span>
              </div>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Direct Access:</span>
                <span>Since the online store is your Lakebase project, you can query features directly with the same PostgreSQL connection used in other labs.</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
