import { useState, useEffect } from 'react'
import { api } from '../api'
import { Cpu, Edit3, Check, X, AlertCircle, Server, Zap, RefreshCw } from '../icons'
import LabBanner from '../LabBanner'

export default function ComputePage() {
  const [branches, setBranches] = useState([])
  const [selectedBranch, setSelectedBranch] = useState('production')
  const [endpoints, setEndpoints] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    api.listBranches().then(setBranches).catch(() => {})
  }, [])

  const loadEndpoints = () => {
    if (!selectedBranch) return
    setLoading(true)
    api.listEndpoints(selectedBranch)
      .then(setEndpoints)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(loadEndpoints, [selectedBranch])

  const handleUpdate = async (e) => {
    e.preventDefault()
    if (!editForm) return
    setUpdating(true)
    try {
      const epId = editForm.name.split('/').pop()
      await api.updateCompute(selectedBranch, epId, {
        min_cu: editForm.min_cu,
        max_cu: editForm.max_cu,
      })
      setEditForm(null)
      loadEndpoints()
    } catch (err) {
      setError(err.message)
    }
    setUpdating(false)
  }

  const spread = editForm ? editForm.max_cu - editForm.min_cu : 0

  return (
    <div>
      <div className="page-header">
        <h2>Autoscaling & Compute</h2>
        <p>
          View and adjust compute endpoints. Lakebase autoscales between min and max CU
          based on workload demand. Scale-to-zero suspends compute after inactivity.
        </p>
      </div>
      <LabBanner pageId="compute" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
          <button className="btn btn-sm btn-secondary" onClick={() => setError(null)}>
            <X size={14} />
          </button>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3><Server size={16} /> Compute Endpoints</h3>
          <div className="btn-row">
            <select
              className="form-select"
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
            >
              {branches.map((b) => (
                <option key={b.branch_id} value={b.branch_id}>{b.branch_id}</option>
              ))}
            </select>
            <button className="btn btn-secondary btn-sm btn-icon" onClick={loadEndpoints}>
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="empty-state empty-state-compact"><p>Loading endpoints...</p></div>
        ) : endpoints.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><Cpu size={36} /></div>
            <p>No endpoints found for this branch.</p>
          </div>
        ) : (
          endpoints.map((ep) => (
            <div key={ep.name} className="list-item-card" style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div className="btn-row">
                  <span className="td-mono-bold" style={{ fontSize: 14 }}>{ep.name.split('/').pop()}</span>
                  <span className={`badge ${ep.state?.includes('ACTIVE') ? 'badge-success' : 'badge-warning'}`}>
                    {ep.state || 'unknown'}
                  </span>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={() => setEditForm({ ...ep })}>
                  <Edit3 size={14} /> Edit Scaling
                </button>
              </div>

              <div className="metrics-row" style={{ marginBottom: 12 }}>
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
                  <div className="metric-value">{ep.endpoint_type?.replace('ENDPOINT_TYPE_', '') || '--'}</div>
                  <div className="metric-label">Type</div>
                </div>
              </div>

              {ep.min_cu != null && (
                <div>
                  <div className="cu-gauge">
                    <div className="cu-gauge-fill" style={{ width: `${((ep.max_cu || 0) / 112) * 100}%` }} />
                  </div>
                  <div className="cu-gauge-labels">
                    <span>0 CU</span>
                    <span>{ep.min_cu}-{ep.max_cu} CU</span>
                    <span>112 CU</span>
                  </div>
                </div>
              )}

              {ep.host && (
                <div className="td-mono-sm" style={{ color: 'var(--text-muted)', marginTop: 10 }}>
                  Host: {ep.host}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {editForm && (
        <div className="card" style={{ borderColor: 'var(--border-accent)' }}>
          <div className="card-header">
            <h3><Edit3 size={16} /> Update Autoscaling Limits</h3>
            <button className="btn btn-secondary btn-sm btn-icon" onClick={() => setEditForm(null)}>
              <X size={14} />
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16, lineHeight: 1.6 }}>
            Autoscaling range: <strong>0.5–64 CU</strong>. The spread (max − min) cannot exceed <strong>16 CU</strong>.
            Each CU provides ~2 GB RAM. Larger fixed-size computes go up to <strong>112 CU</strong>.
          </p>
          <form onSubmit={handleUpdate}>
            <div className="form-row">
              <div className="form-group">
                <label>Min CU ({editForm.min_cu})</label>
                <input
                  type="range"
                  step="0.5"
                  min="0.5"
                  max="64"
                  value={editForm.min_cu}
                  onChange={(e) => setEditForm({ ...editForm, min_cu: parseFloat(e.target.value) })}
                />
                <div className="slider-labels">
                  <span>0.5</span><span>16</span><span>32</span><span>48</span><span>64</span>
                </div>
              </div>
              <div className="form-group">
                <label>Max CU ({editForm.max_cu})</label>
                <input
                  type="range"
                  step="0.5"
                  min="0.5"
                  max="64"
                  value={editForm.max_cu}
                  onChange={(e) => setEditForm({ ...editForm, max_cu: parseFloat(e.target.value) })}
                />
                <div className="slider-labels">
                  <span>0.5</span><span>16</span><span>32</span><span>48</span><span>64</span>
                </div>
              </div>
            </div>

            {/* Visual preview */}
            <div style={{ marginBottom: 16 }}>
              <div className="cu-gauge-labels" style={{ marginBottom: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                <span>Preview</span>
                <span className="td-mono">{editForm.min_cu}-{editForm.max_cu} CU &middot; {(editForm.min_cu * 2).toFixed(0)}-{(editForm.max_cu * 2).toFixed(0)} GB RAM</span>
              </div>
              <div className="cu-gauge">
                <div className="cu-gauge-fill" style={{ width: `${((editForm.max_cu || 0) / 112) * 100}%`, marginLeft: `${((editForm.min_cu || 0) / 112) * 100}%` }} />
              </div>
              <div className="cu-gauge-labels">
                <span>0 CU</span>
                <span>112 CU</span>
              </div>
            </div>

            {spread > 16 && (
              <div className="info-box danger" style={{ marginBottom: 12 }}>
                <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                <span>Spread is {spread.toFixed(1)} CU (max allowed: 16 CU)</span>
              </div>
            )}

            <div className="btn-row">
              <button className="btn btn-primary" disabled={updating || spread > 16}>
                <Check size={14} />
                {updating ? 'Updating...' : 'Apply Changes'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setEditForm(null)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3><Zap size={16} /> Compute Sizing Reference</h3>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>CU</th><th>RAM</th><th>Max Connections*</th><th>Use Case</th></tr>
          </thead>
          <tbody>
            <tr><td><span className="badge badge-cyan">0.5</span></td><td>~1 GB</td><td>~105</td><td>Dev/test, low traffic</td></tr>
            <tr><td><span className="badge badge-info">4</span></td><td>~8 GB</td><td>~894</td><td>Small production apps</td></tr>
            <tr><td><span className="badge badge-purple">8</span></td><td>~16 GB</td><td>~1,795</td><td>Medium production</td></tr>
            <tr><td><span className="badge badge-warning">16</span></td><td>~32 GB</td><td>~3,597</td><td>High-throughput apps</td></tr>
            <tr><td><span className="badge badge-accent">32</span></td><td>~64 GB</td><td>~3,993</td><td>Large production</td></tr>
            <tr><td><span className="badge badge-accent">64</span></td><td>~128 GB</td><td>~3,993</td><td>Maximum autoscale</td></tr>
            <tr><td><span className="badge badge-accent">80</span></td><td>~160 GB</td><td>~3,993</td><td>Large fixed-size</td></tr>
            <tr><td><span className="badge badge-accent">96</span></td><td>~192 GB</td><td>~3,993</td><td>Large fixed-size</td></tr>
            <tr><td><span className="badge badge-accent">112</span></td><td>~224 GB</td><td>~3,993</td><td>Maximum fixed-size</td></tr>
          </tbody>
        </table>
        <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 10 }}>
          *Connection counts are approximate and set by the compute size. Autoscaling ranges up to 64 CU with a max−min spread ≤ 16 CU; larger fixed-size computes are available up to 112 CU.
        </p>
      </div>
    </div>
  )
}
