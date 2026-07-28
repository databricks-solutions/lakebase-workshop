import { useState, useEffect } from 'react'
import { api } from '../api'
import { useAppContext } from '../App'
import {
  RefreshCw, Server, Shield, Database, AlertCircle, ChevronRight, Activity, Cpu,
} from '../icons'
import LabBanner from '../LabBanner'

function cleanState(raw) {
  if (!raw) return 'unknown'
  const dot = raw.lastIndexOf('.')
  return dot >= 0 ? raw.slice(dot + 1) : raw
}

export default function HighAvailabilityPage() {
  const ctx = useAppContext()
  const branchId = ctx?.config?.branch_id || 'production'
  const [topo, setTopo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setTopo(await api.computeTopology(branchId))
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [branchId])

  const primary = topo?.endpoints?.find(e => e.is_primary)
  const replicas = topo?.endpoints?.filter(e => !e.is_primary) || []

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>High Availability & Read Replicas</h2>
            <p>
              Inspect the compute topology for your branch, understand failover behavior, and see
              how read replicas offload read traffic. HA and read replicas are configured from the
              Lakebase UI &mdash; this page is read-only inspection.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'icon-spin' : ''} /> {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="ha" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* Topology summary */}
      <div className="metrics-row metrics-row-4">
        <div className="metric-card">
          <div className="metric-icon"><Server size={18} /></div>
          <div className="metric-value">{topo?.primary_count ?? '--'}</div>
          <div className="metric-label">Primary (read-write)</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Database size={18} /></div>
          <div className="metric-value">{topo?.read_replica_count ?? '--'}</div>
          <div className="metric-label">Read Replicas</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Activity size={18} /></div>
          <div className="metric-value">{topo ? (topo.has_read_routing ? 'Yes' : 'No') : '--'}</div>
          <div className="metric-label">Read Routing Host</div>
        </div>
        <div className="metric-card">
          <div className="metric-icon"><Cpu size={18} /></div>
          <div className="metric-value">{topo?.endpoints?.length ?? '--'}</div>
          <div className="metric-label">Total Endpoints</div>
        </div>
      </div>

      {/* Endpoints */}
      <div className="card">
        <div className="card-header">
          <h3><Server size={16} /> Compute Endpoints ({branchId})</h3>
        </div>
        {loading ? (
          <div className="empty-state" style={{ padding: 20 }}><p>Loading topology...</p></div>
        ) : !topo?.endpoints?.length ? (
          <div className="empty-state">
            <div className="empty-icon"><Server size={32} /></div>
            <p>No endpoints found. Run the setup notebook to create your project, then refresh.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Role</th><th>Type</th><th>State</th><th>Host</th><th>Autoscaling</th></tr>
            </thead>
            <tbody>
              {topo.endpoints.map((e, i) => (
                <tr key={i}>
                  <td>
                    {e.is_primary
                      ? <span className="badge badge-success">Primary</span>
                      : <span className="badge badge-info">Read Replica</span>}
                  </td>
                  <td className="td-mono-xs">{(e.endpoint_type || '').replace(/^.*\./, '') || '--'}</td>
                  <td><span className={`badge ${cleanState(e.state).includes('ACTIVE') ? 'badge-success' : 'badge-warning'}`}>{cleanState(e.state)}</span></td>
                  <td className="td-mono-xs" style={{ wordBreak: 'break-all' }}>
                    {e.host || '--'}
                    {e.read_only_host && (
                      <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>ro: {e.read_only_host}</div>
                    )}
                  </td>
                  <td className="td-mono-xs">{e.min_cu ?? '--'} - {e.max_cu ?? '--'} CU</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {topo?.has_read_routing && (
          <div className="info-box info" style={{ marginTop: 12 }}>
            <span style={{ fontWeight: 600 }}>Read routing:</span>
            <span>The primary exposes a separate <code>read_only_host</code>. Point read-only workloads at it to offload the read-write endpoint.</span>
          </div>
        )}
      </div>

      {/* How HA works */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} /> How High Availability Works</h3>
        </div>
        <div className="flow-diagram flow-5">
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Server size={28} style={{ color: 'var(--accent)' }} /></div>
            <div className="flow-box-title">Primary</div>
            <div className="flow-box-subtitle">Read-write</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Activity size={28} style={{ color: 'var(--teal)' }} /></div>
            <div className="flow-box-title">Automatic Failover</div>
            <div className="flow-box-subtitle">Multi-AZ</div>
          </div>
          <div className="flow-arrow"><ChevronRight size={32} /></div>
          <div className="flow-box">
            <div style={{ marginBottom: 8 }}><Server size={28} style={{ color: 'var(--blue)' }} /></div>
            <div className="flow-box-title">Standby / Replica</div>
            <div className="flow-box-subtitle">Promoted on failure</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Failover:</span>
            <span>With HA enabled, a standby in another availability zone takes over automatically if the primary fails. The endpoint host stays stable; clients reconnect and continue.</span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Read replicas vs. standalone read compute:</span>
            <span>A read replica shares the branch's storage and serves read-only queries close to real time. A standalone read-only compute is a separate endpoint you size independently. Use replicas to scale reads without impacting write throughput.</span>
          </div>
          <div className="info-box warning">
            <span style={{ fontWeight: 600 }}>Configuration:</span>
            <span>HA and read replicas are enabled from the Lakebase UI (Project settings / Compute). There is no SDK enablement path today, so this console inspects but does not change the topology.</span>
          </div>
          <div className="info-box info">
            <span style={{ fontWeight: 600 }}>Disaster recovery:</span>
            <span>HA protects against zone failure within a region. Cross-region / cross-workspace disaster recovery is a separate, roadmap capability &mdash; see the Backup &amp; Recovery lab for point-in-time restore within a region.</span>
          </div>
        </div>
      </div>
    </div>
  )
}
