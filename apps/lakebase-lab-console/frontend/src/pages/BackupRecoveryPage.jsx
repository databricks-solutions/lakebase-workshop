import { useState, useEffect } from 'react'
import { api } from '../api'
import {
  Shield, GitBranch, Database, RefreshCw, AlertCircle,
  Clock, Plus, ChevronRight, Activity
} from '../icons'
import LabBanner from '../LabBanner'

export default function BackupRecoveryPage() {
  const [branches, setBranches] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [creating, setCreating] = useState(false)
  const [checkpointName, setCheckpointName] = useState('')
  const [sourceBranch, setSourceBranch] = useState('production')
  const [createResult, setCreateResult] = useState(null)

  const loadBranches = async () => {
    setLoading(true)
    try {
      const b = await api.listBranches()
      setBranches(b)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadBranches() }, [])

  const createCheckpoint = async (e) => {
    e.preventDefault()
    if (!checkpointName.trim()) return
    setCreating(true)
    setCreateResult(null)
    try {
      const name = checkpointName.startsWith('lab-') ? checkpointName : `lab-${checkpointName}`
      await api.createBranch({
        branch_id: name,
        source_branch: sourceBranch,
      })
      setCreateResult({ success: true, message: `Checkpoint branch "${name}" created from ${sourceBranch}` })
      setCheckpointName('')
      loadBranches()
    } catch (e) {
      setCreateResult({ success: false, message: e.message })
    }
    setCreating(false)
  }

  // Temporary branches auto-delete; the API reports this via expire_time (a TTL
  // was set at create). Non-expiring checkpoints have no expire_time.
  const isTemporary = (b) => b.expire_time && b.expire_time !== 'None'

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Backup & Recovery</h2>
            <p>
              Lakebase provides built-in data protection through continuous WAL archival,
              point-in-time restore, managed snapshots, and instant copy-on-write branches.
              This page creates <strong>checkpoint branches</strong> — snapshots and PITR
              are driven from Backup &amp; Restore in the Lakebase App.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadBranches} disabled={loading}>
            <RefreshCw size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="backup" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* Backup Architecture */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} /> Backup Architecture</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12, lineHeight: 1.6 }}>
          Backups are always on — you don't configure them, you just set the history window. Lakebase
          provides multiple layers of data protection built into every project. Note that recovery
          storage <strong>is billed</strong> (as of Jun 1, 2026): primary data, PITR history, and
          snapshots are three separate storage components, so a longer window and more snapshots cost more.
        </p>
        <table className="data-table">
          <thead>
            <tr><th>Feature</th><th>How It Works</th><th>Use Case</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><span className="badge badge-info">WAL Archival</span></td>
              <td>Write-ahead logs continuously streamed to durable storage</td>
              <td>Foundation for PITR</td>
            </tr>
            <tr>
              <td><span className="badge badge-success">Point-in-Time Restore</span></td>
              <td>New root branch from any second within the configured window (up to 30 days)</td>
              <td>Accidental data corruption or deletion</td>
            </tr>
            <tr>
              <td><span className="badge badge-purple">Snapshots</span></td>
              <td>Managed capture of a root branch, manual or scheduled (Lakebase App &rarr; Backup &amp; Restore)</td>
              <td>Routine backups; restore points before UI changes</td>
            </tr>
            <tr>
              <td><span className="badge badge-warning">Checkpoint Branches</span></td>
              <td>Copy-on-write branch as a named restore point (instant, no TTL)</td>
              <td>Scripted pre-migration safety net</td>
            </tr>
            <tr>
              <td><span className="badge badge-cyan">Branch TTL</span></td>
              <td>Branches auto-delete after a configurable time</td>
              <td>Dev/test cleanup</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="grid-2col">
        {/* Create Checkpoint */}
        <div className="card">
          <div className="card-header">
            <h3><Plus size={16} /> Create Checkpoint Branch</h3>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12, lineHeight: 1.6 }}>
            Create a named restore point before risky changes. Checkpoint branches are instant,
            non-expiring, and cost no additional storage until data diverges. This is the
            scriptable equivalent of a snapshot — the managed Snapshots feature lives in the
            Lakebase App under Backup &amp; Restore.
          </p>
          {createResult && (
            <div className={`info-box ${createResult.success ? 'info' : 'danger'}`} style={{ marginBottom: 12 }}>
              <span>{createResult.message}</span>
            </div>
          )}
          <form onSubmit={createCheckpoint}>
            <div className="form-group">
              <label>Checkpoint Name</label>
              <input
                value={checkpointName}
                onChange={(e) => setCheckpointName(e.target.value)}
                placeholder="checkpoint-pre-migration"
              />
              <div className="setup-hint">
                Prefixed with "lab-" automatically if not present
              </div>
            </div>
            <div className="form-group">
              <label>Source Branch</label>
              <select
                value={sourceBranch}
                onChange={(e) => setSourceBranch(e.target.value)}
                className="form-select"
                style={{ width: '100%' }}
              >
                {branches.length > 0 ? (
                  branches.map((b) => (
                    <option key={b.branch_id} value={b.branch_id}>{b.branch_id}</option>
                  ))
                ) : (
                  <option value="production">production</option>
                )}
              </select>
            </div>
            <button className="btn btn-primary btn-sm" type="submit" disabled={creating || !checkpointName.trim()} style={{ width: '100%' }}>
              <Shield size={14} /> {creating ? 'Creating...' : 'Create Checkpoint'}
            </button>
          </form>
        </div>

        {/* Current Branches */}
        <div className="card">
          <div className="card-header">
            <h3><GitBranch size={16} /> Current Branches</h3>
            <span className="badge badge-info">{branches.length} branches</span>
          </div>
          {loading ? (
            <div className="empty-state empty-state-compact"><p>Loading...</p></div>
          ) : branches.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No branches found</p></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {branches.map((b, i) => (
                <div key={i} className="list-item-card" style={{
                  padding: '10px 14px',
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                  <div>
                    <div className="td-mono-bold" style={{ fontSize: 13 }}>{b.branch_id}</div>
                    {b.source_branch && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>from: {b.source_branch}</div>
                    )}
                  </div>
                  <div className="btn-row">
                    {isTemporary(b) ? (
                      <span className="badge badge-warning" style={{ fontSize: 10 }}>Auto-deletes</span>
                    ) : (
                      <span className="badge badge-success" style={{ fontSize: 10 }}>Persistent</span>
                    )}
                    <span className={`badge ${b.state?.includes('ACTIVE') ? 'badge-success' : 'badge-info'}`} style={{ fontSize: 10 }}>{b.state || 'active'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recovery Guide */}
      <div className="card">
        <div className="card-header">
          <h3><Activity size={16} /> Recovery Workflow</h3>
        </div>
        <div className="flow-diagram flow-5">
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Shield size={28} style={{ color: 'var(--blue)' }} /></div>
            <div className="flow-box-title">Create Checkpoint</div>
            <div className="flow-box-subtitle">Named restore point</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><GitBranch size={28} style={{ color: 'var(--warning)' }} /></div>
            <div className="flow-box-title">Work Branch</div>
            <div className="flow-box-subtitle">Risky changes</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Database size={28} style={{ color: 'var(--success)' }} /></div>
            <div className="flow-box-title">Recover</div>
            <div className="flow-box-subtitle">Branch from checkpoint</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Step 1:</span>
            <span>Create a checkpoint branch from production (no TTL) as a named safety net.</span>
          </div>
          <div className="info-box warning">
            <span style={{ fontWeight: 600 }}>Step 2:</span>
            <span>Create a separate work branch (with TTL). Run your migration, bulk delete, or schema change there.</span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Step 3:</span>
            <span>If something goes wrong, create a new branch from the checkpoint. Data is fully intact.</span>
          </div>
        </div>
      </div>

      {/* PITR */}
      <div className="card">
        <div className="card-header">
          <h3><Clock size={16} /> Point-in-Time Recovery (PITR)</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12, lineHeight: 1.6 }}>
          For production scenarios where you need to recover to an exact moment, Lakebase
          supports PITR by replaying WAL segments to a target timestamp. The documented path is the
          <strong> Backup &amp; Restore</strong> flow in the Lakebase App, which provisions a
          <strong> new root branch</strong> at the chosen point in time. A project can have at most
          <strong> 3 root branches</strong>. Via the SDK, use the <code>source_branch_time</code> field
          on <code>BranchSpec</code>.
        </p>
        <div className="code-block">{`from datetime import datetime, timezone, timedelta
from databricks.sdk.service.postgres import Branch, BranchSpec
from google.protobuf.timestamp_pb2 import Timestamp

# Recover to 30 minutes ago
target = datetime.now(timezone.utc) - timedelta(minutes=30)

ts = Timestamp()
ts.FromDatetime(target)

w.postgres.create_branch(
    parent=f"projects/{PROJECT_ID}",
    branch=Branch(
        spec=BranchSpec(
            source_branch=f"projects/{PROJECT_ID}/branches/production",
            source_branch_time=ts,
        )
    ),
    branch_id="pitr-recovery",
).wait()`}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Recovery Window:</span>
            <span>Default 7 days, maximum 30 days. Configurable at the project level. You can recover to any second within the window.</span>
          </div>
        </div>
      </div>

      {/* Best Practices */}
      <div className="card">
        <div className="card-header">
          <h3>Best Practices</h3>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>Scenario</th><th>Recommended Approach</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Before a scripted schema migration</td>
              <td>Create a checkpoint branch (instant; shares storage until data diverges)</td>
            </tr>
            <tr>
              <td>Routine backups</td>
              <td>Set a snapshot schedule on the root branch in the Lakebase App</td>
            </tr>
            <tr>
              <td>Accidental DELETE/UPDATE</td>
              <td>PITR to the second before the mistake</td>
            </tr>
            <tr>
              <td>Testing destructive operations</td>
              <td>Create a work branch with TTL, test there, delete when done</td>
            </tr>
            <tr>
              <td>Compliance / audit retention</td>
              <td>Set the history window to its 30-day maximum at the project level</td>
            </tr>
            <tr>
              <td>Disaster recovery drill</td>
              <td>Periodically create a branch from PITR, verify data integrity</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
