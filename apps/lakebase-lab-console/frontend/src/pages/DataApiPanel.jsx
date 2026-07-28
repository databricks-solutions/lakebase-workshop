import { useState, useEffect } from 'react'
import { api } from '../api'
import {
  RefreshCw, Database, Terminal, Play, Shield, AlertCircle, Check, Clock, Key,
} from '../icons'
import LabBanner from '../LabBanner'

function StatusPill({ ok, label }) {
  return (
    <span className={`badge ${ok ? 'badge-success' : 'badge-warning'}`}>
      {ok ? <Check size={11} /> : <AlertCircle size={11} />} {label}
    </span>
  )
}

/**
 * Data API (PostgREST) panel — rendered inside the unified API Tester page under
 * the "Data API" target. Calls the external Lakebase Data API as the app's
 * Service Principal (a valid non-owner caller).
 */
export default function DataApiPanel() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [url, setUrl] = useState('')
  const [resource, setResource] = useState('api_clients')
  const [method, setMethod] = useState('GET')
  const [query, setQuery] = useState('select=id,name,company&id=gte.2')
  const [body, setBody] = useState('')
  const [resp, setResp] = useState(null)
  const [respErr, setRespErr] = useState(false)
  const [calling, setCalling] = useState(false)
  const [elapsed, setElapsed] = useState(null)

  const [prep, setPrep] = useState(null)
  const [prepping, setPrepping] = useState(false)

  const loadStatus = async () => {
    setLoading(true)
    setError(null)
    try {
      setStatus(await api.dataApiStatus())
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadStatus() }, [])

  const runPrepare = async () => {
    setPrepping(true)
    setPrep(null)
    try {
      setPrep(await api.dataApiPrepare())
      loadStatus()
    } catch (e) {
      setPrep({ ok: false, errors: [{ error: e.message }] })
    }
    setPrepping(false)
  }

  const sendCall = async () => {
    setCalling(true)
    setResp(null)
    setRespErr(false)
    const start = performance.now()
    try {
      const payload = { url, resource, method, query }
      if (method === 'POST' || method === 'PATCH') {
        try { payload.body = body.trim() ? JSON.parse(body) : {} }
        catch { setRespErr(true); setResp('Body is not valid JSON'); setCalling(false); return }
      }
      const r = await api.dataApiCall(payload)
      setElapsed(Math.round(performance.now() - start))
      setRespErr(r.status >= 400)
      setResp(`${r.method || method} ${r.url}\n\n[${r.status}]\n${r.body}`)
    } catch (e) {
      setElapsed(Math.round(performance.now() - start))
      setRespErr(true)
      setResp(e.message)
    }
    setCalling(false)
  }

  const enabled = status?.enabled

  return (
    <>
      <LabBanner pageId="data-api" />
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 16px', lineHeight: 1.6 }}>
        Call the external Lakebase Data API (PostgREST) as the app's <strong>Service Principal</strong>,
        a non-owner identity &mdash; the project owner cannot call the Data API.
      </p>

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} /><p>{error}</p>
        </div>
      )}

      {/* Status */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} /> Status</h3>
          <div className="btn-row">
            {status && (
              <>
                <StatusPill ok={status.enabled} label={status.enabled ? 'API enabled' : 'API not enabled'} />
                <StatusPill ok={status.sp_role_exists} label="SP role" />
                <StatusPill ok={status.sp_can_assume} label="Assumable" />
              </>
            )}
            <button className="btn btn-secondary btn-sm" onClick={loadStatus} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'icon-spin' : ''} /> {loading ? 'Checking...' : 'Refresh'}
            </button>
          </div>
        </div>
        {!enabled ? (
          <div className="info-box warning">
            <span style={{ fontWeight: 600 }}>Enable the Data API first:</span>
            <span>
              In your Lakebase project, open the <strong>Data API</strong> tab and click
              <strong> Enable Data API</strong>. That creates the <code>authenticator</code> role and
              exposes the <code>public</code> schema. Then copy the API URL below. See the Data API lab
              (<code>labs/data-api/</code>) for the full walkthrough.
            </span>
          </div>
        ) : (
          <div style={{ fontSize: 13 }}>
            <div className="detail-row">
              <span className="detail-label">App SP</span>
              <span className="detail-value detail-value-mono" style={{ fontSize: 11 }}>{status.sp_app_id || '--'}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Exposed schema</span>
              <span className="detail-value detail-value-mono">{status.schema}</span>
            </div>
            {!status.sp_can_assume && (
              <div className="info-box info" style={{ marginTop: 12 }}>
                <span style={{ fontWeight: 600 }}>Prepare the app SP:</span>
                <span>The Data API is enabled but the app's Service Principal isn't set up as an assumable role yet. Prepare it below (or run the SQL as the project owner).</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Prepare SP role */}
      {enabled && (
        <div className="card">
          <div className="card-header">
            <h3><Key size={16} /> Prepare App SP Access</h3>
            <button className="btn btn-primary btn-sm" onClick={runPrepare} disabled={prepping}>
              <Play size={14} /> {prepping ? 'Preparing...' : 'Prepare SP role'}
            </button>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
            Creates a Postgres role for the app's Service Principal, lets <code>authenticator</code> assume
            it, and grants access to your schema. Role management usually requires the project owner &mdash;
            if this fails, run the SQL below in a notebook as the owner.
          </p>
          {prep && (
            <div className={`info-box ${prep.ok ? 'info' : 'warning'}`} style={{ marginBottom: 12 }}>
              <span style={{ fontWeight: 600 }}>{prep.ok ? 'Prepared:' : 'Some statements failed:'}</span>
              <span>{prep.ok ? 'The app SP can now call the Data API.' : (prep.note || 'See errors and run the SQL manually.')}</span>
            </div>
          )}
          {prep?.errors?.length > 0 && (
            <div className="api-response error" style={{ marginBottom: 12 }}>
              {prep.errors.map((e) => `${e.statement || ''}\n  -> ${e.error}`).join('\n\n')}
            </div>
          )}
          {prep?.sql && <div className="code-block">{prep.sql}</div>}
        </div>
      )}

      {/* Request builder */}
      <div className="card">
        <div className="card-header">
          <h3><Terminal size={16} /> Call the Data API</h3>
        </div>
        <div className="form-group">
          <label>Data API URL (from the API tab)</label>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://<project>.<region>.databricks.com/..." />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Method</label>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option>GET</option><option>POST</option><option>PATCH</option><option>DELETE</option>
            </select>
          </div>
          <div className="form-group">
            <label>Resource (table)</label>
            <input value={resource} onChange={(e) => setResource(e.target.value)} placeholder="api_clients" />
          </div>
        </div>
        <div className="form-group">
          <label>Query string (PostgREST filters)</label>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="select=id,name&id=gte.2&order=name.asc&limit=10" className="td-mono-sm" />
        </div>
        {(method === 'POST' || method === 'PATCH') && (
          <div className="form-group">
            <label>Body (JSON)</label>
            <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} placeholder='{"name":"New Client","email":"new@example.com"}' className="td-mono-sm" />
          </div>
        )}
        <button className="btn btn-primary" onClick={sendCall} disabled={calling || !url}>
          <Play size={14} /> {calling ? 'Sending...' : 'Send Request'}
        </button>
        {!url && <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--text-muted)' }}>Paste the API URL to enable.</span>}
      </div>

      {resp !== null && (
        <div className="card">
          <div className="card-header">
            <h3>
              {respErr ? <AlertCircle size={16} style={{ color: 'var(--danger)' }} /> : <Check size={16} style={{ color: 'var(--success)' }} />}
              Response
            </h3>
            {elapsed !== null && <span className="badge badge-info"><Clock size={11} /> {elapsed}ms</span>}
          </div>
          <div className={`api-response ${respErr ? 'error' : ''}`}>{resp}</div>
        </div>
      )}

      {/* Governance caveat */}
      <div className="card">
        <div className="card-header">
          <h3><Database size={16} /> Filters & Governance</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
          Common PostgREST operators: <code>eq</code>, <code>neq</code>, <code>gte</code>, <code>lte</code>,
          <code>like</code>, <code>in</code>. Embed related resources with
          <code>select=id,name,projects(id,name)</code>. Paginate with <code>limit</code>/<code>offset</code>,
          sort with <code>order=name.asc</code>.
        </p>
        <div className="info-box danger">
          <span style={{ fontWeight: 600 }}>Governance:</span>
          <span>The Data API talks directly to Postgres and is governed by Postgres roles + row-level security, <strong>not</strong> Unity Catalog. It is internet-reachable, so enable RLS on every exposed table and never expose data through the owner account.</span>
        </div>
      </div>
    </>
  )
}
