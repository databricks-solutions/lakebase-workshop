import { useState, useEffect } from 'react'
import { api } from '../api'
import { GitBranch, Plus, Trash2, AlertCircle, X, Shield, Clock, Check, RefreshCw, ExternalLink } from '../icons'
import LabBanner from '../LabBanner'

export default function BranchManager() {
  const [branches, setBranches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ branch_id: 'lab-', source_branch: 'production', ttl_hours: 24 })
  const [creating, setCreating] = useState(false)

  const load = () => {
    setLoading(true)
    api.listBranches()
      .then(setBranches)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.createBranch(form)
      setShowCreate(false)
      setForm({ branch_id: 'lab-', source_branch: 'production', ttl_hours: 24 })
      load()
    } catch (err) {
      setError(err.message)
    }
    setCreating(false)
  }

  const handleDelete = async (id) => {
    if (!confirm(`Delete branch "${id}"? This cannot be undone.`)) return
    try {
      await api.deleteBranch(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>Branch Manager</h2>
        <p>
          Create isolated database environments with copy-on-write storage.
          Each branch gets its own compute endpoint and full PostgreSQL instance.
        </p>
      </div>
      <LabBanner pageId="branches" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
          <button className="btn btn-sm btn-secondary btn-icon" onClick={() => setError(null)}>
            <X size={14} />
          </button>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3><GitBranch size={16} /> Branches ({branches.length})</h3>
          <div className="btn-row">
            <button className="btn btn-secondary btn-sm btn-icon" onClick={load}>
              <RefreshCw size={14} />
            </button>
            <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(!showCreate)}>
              <Plus size={14} /> New Branch
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={handleCreate} className="form-inset" style={{ marginBottom: 20 }}>
            <div className="form-row">
              <div className="form-group">
                <label>Branch ID (must start with lab-)</label>
                <input
                  value={form.branch_id}
                  onChange={(e) => setForm({ ...form, branch_id: e.target.value })}
                  placeholder="lab-my-feature"
                  pattern="^lab-[a-z0-9-]{1,50}$"
                  required
                />
              </div>
              <div className="form-group">
                <label>Source Branch</label>
                <select value={form.source_branch} onChange={(e) => setForm({ ...form, source_branch: e.target.value })}>
                  {branches.map((b) => (
                    <option key={b.branch_id} value={b.branch_id}>{b.branch_id}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-group">
              <label>TTL (hours)</label>
              <input
                type="number"
                value={form.ttl_hours}
                onChange={(e) => setForm({ ...form, ttl_hours: parseInt(e.target.value) || 24 })}
                min={1}
                max={720}
              />
            </div>
            <div className="btn-row">
              <button className="btn btn-primary" disabled={creating}>
                <Check size={14} />
                {creating ? 'Creating...' : 'Create Branch'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <div className="empty-state empty-state-compact"><p>Loading branches...</p></div>
        ) : branches.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><GitBranch size={36} /></div>
            <p>No branches found. Is LAKEBASE_PROJECT_ID configured?</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Branch ID</th>
                <th>State</th>
                <th>Default</th>
                <th>Protected</th>
                <th>Expires</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {branches.map((b) => (
                <tr key={b.branch_id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <GitBranch size={14} style={{ color: 'var(--text-muted)' }} />
                      <span className="td-mono-bold">{b.branch_id}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${b.state?.includes('ACTIVE') ? 'badge-success' : 'badge-warning'}`}>
                      {b.state || 'unknown'}
                    </span>
                  </td>
                  <td>
                    {b.is_default && <Check size={14} style={{ color: 'var(--success)' }} />}
                  </td>
                  <td>
                    {b.is_protected && <Shield size={14} style={{ color: 'var(--warning)' }} />}
                  </td>
                  <td>
                    {b.expire_time && b.expire_time !== 'None' ? (
                      <span className="td-mono-sm" style={{ color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Clock size={12} /> {b.expire_time}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>--</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {b.branch_id.startsWith('lab-') && (
                      <button className="btn btn-danger btn-xs" onClick={() => handleDelete(b.branch_id)}>
                        <Trash2 size={12} /> Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h3>What is Branching?</h3>
          <a
            className="btn btn-secondary btn-sm"
            href="https://docs.databricks.com/aws/en/oltp/projects/branches"
            target="_blank"
            rel="noopener noreferrer"
          >
            Docs <ExternalLink size={12} />
          </a>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, lineHeight: 1.7 }}>
          Branching in Lakebase lets you version, test, and evolve your data environment safely —
          similar to branching your code in Git. You can instantly create isolated, fully functional
          branches for development, experimentation, or testing schema changes, without impacting
          production workloads.
        </p>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 14, lineHeight: 1.7 }}>
          Lakebase uses <strong>copy-on-write</strong> storage. A new branch inherits schema and data
          from its parent via shared pointers — only modified data is stored separately. Branch
          creation is instant, and you only pay for what actually changes.
        </p>

        <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
          Copy-on-write storage
        </h4>
        <div className="code-block">{`production branch                child branch (at creation)
┌─────────────────┐       ┌─────────────────┐
│  [Data A]       │◄──────│  → Data A       │  (shared)
│  [Data B]       │◄──────│  → Data B       │  (shared)
│  [Data C]       │◄──────│  → Data C       │  (shared)
└─────────────────┘       └─────────────────┘

After modifying data in child branch:
┌─────────────────┐       ┌─────────────────┐
│  [Data A]       │◄──────│  → Data A       │  (shared)
│  [Data B]       │       │  [Data B']      │  (changed)
│  [Data C]       │◄──────│  → Data C       │  (shared)
└─────────────────┘       └─────────────────┘
                          Only changed data is stored separately`}</div>

        <h4 style={{ fontSize: 13, fontWeight: 600, margin: '16px 0 8px', color: 'var(--text-primary)' }}>
          Project hierarchy
        </h4>
        <div className="code-block">{`Project
  └── production (default, protected)
        ├── lab-feature-a (TTL: 24h)
        │     └── Compute: 0.5-4 CU
        └── lab-feature-b (TTL: 48h)
              └── Compute: 0.5-4 CU`}</div>
      </div>
    </div>
  )
}
