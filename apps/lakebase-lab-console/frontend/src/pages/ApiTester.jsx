import { useState } from 'react'
import { Terminal, Play, Clock, AlertCircle, Check, Server, Database } from '../icons'
import DataApiPanel from './DataApiPanel'
import { isSafeApiPath } from '../util/apiSafety'

const PRESETS = [
  { label: 'Health Check', method: 'GET', path: '/api/health' },
  { label: 'DB Test', method: 'GET', path: '/api/dbtest' },
  { label: 'App Config', method: 'GET', path: '/api/config' },
  { label: 'List Branches', method: 'GET', path: '/api/branches' },
  { label: 'List Products', method: 'GET', path: '/api/data/products' },
  { label: 'Table Stats', method: 'GET', path: '/api/data/stats' },
  { label: 'Audit Log', method: 'GET', path: '/api/data/audit' },
  { label: 'Agent Sessions', method: 'GET', path: '/api/agent/sessions' },
  { label: 'Create Event', method: 'POST', path: '/api/data/events', body: { event_type: 'test', source: 'api-tester', payload: { hello: 'world' } } },
  { label: 'Create Product', method: 'POST', path: '/api/data/products', body: { name: 'Test Product', price: 9.99, category: 'General', stock_quantity: 10 } },
]

function ConsolePanel() {
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('/api/health')
  const [body, setBody] = useState('')
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(null)

  const send = async () => {
    if (!isSafeApiPath(path)) {
      setError(true)
      setResponse('Path must be a same-origin API path starting with /api/ (no absolute URLs, "//", or "..").')
      return
    }
    setLoading(true)
    setResponse(null)
    setError(false)
    const start = performance.now()
    try {
      const opts = { method, headers: { 'Content-Type': 'application/json' } }
      if (method !== 'GET' && body.trim()) {
        opts.body = body
      }
      const res = await fetch(path, opts)
      const data = await res.json()
      setElapsed(Math.round(performance.now() - start))
      if (!res.ok) {
        setError(true)
        setResponse(JSON.stringify({ status: res.status, ...data }, null, 2))
      } else {
        setResponse(JSON.stringify(data, null, 2))
      }
    } catch (e) {
      setElapsed(Math.round(performance.now() - start))
      setError(true)
      setResponse(e.message)
    }
    setLoading(false)
  }

  const applyPreset = (preset) => {
    setMethod(preset.method)
    setPath(preset.path)
    setBody(preset.body ? JSON.stringify(preset.body, null, 2) : '')
    setResponse(null)
  }

  return (
    <>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 16px', lineHeight: 1.6 }}>
        Exercise the Lab Console's own FastAPI routes directly from the browser using the app session.
        Useful for debugging and understanding the Lakebase integration.
      </p>

      <div className="card">
        <div className="card-header">
          <h3><Terminal size={16} /> Presets</h3>
        </div>
        <div className="btn-row" style={{ flexWrap: 'wrap' }}>
          {PRESETS.map((p) => (
            <button key={p.label} className="btn btn-secondary btn-sm" onClick={() => applyPreset(p)}>
              <span className={`badge ${p.method === 'GET' ? 'badge-success' : 'badge-warning'}`}>{p.method}</span>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Request</h3>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Method</label>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option>GET</option><option>POST</option><option>PUT</option>
              <option>PATCH</option><option>DELETE</option>
            </select>
          </div>
          <div className="form-group">
            <label>Path</label>
            <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/api/..." />
          </div>
        </div>
        {method !== 'GET' && (
          <div className="form-group">
            <label>Body (JSON)</label>
            <textarea
              rows={5}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder='{"key": "value"}'
              className="td-mono-sm"
            />
          </div>
        )}
        <button className="btn btn-primary" onClick={send} disabled={loading}>
          <Play size={14} />
          {loading ? 'Sending...' : 'Send Request'}
        </button>
      </div>

      {response !== null && (
        <div className="card">
          <div className="card-header">
            <h3>
              {error ? <AlertCircle size={16} style={{ color: 'var(--danger)' }} /> : <Check size={16} style={{ color: 'var(--success)' }} />}
              Response
            </h3>
            {elapsed !== null && (
              <span className="badge badge-info">
                <Clock size={11} /> {elapsed}ms
              </span>
            )}
          </div>
          <div className={`api-response ${error ? 'error' : ''}`}>
            {response}
          </div>
        </div>
      )}
    </>
  )
}

const TARGETS = [
  { id: 'dataapi', label: 'Data API', Icon: Database },
  { id: 'console', label: 'Console API', Icon: Server },
]

export default function ApiTester() {
  const [target, setTarget] = useState('dataapi')

  return (
    <div>
      <div className="page-header">
        <h2>API Tester</h2>
        <p>
          The <strong>Data API</strong> is Lakebase's built-in REST layer (PostgREST) — query your
          Postgres tables over HTTPS with no backend to run. The <strong>Console API</strong> is this
          Lab Console's own FastAPI backend, handy for debugging the integration.
        </p>
      </div>

      <div className="btn-row" style={{ marginBottom: 16 }}>
        {TARGETS.map((t) => (
          <button
            key={t.id}
            className={`btn btn-sm ${target === t.id ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTarget(t.id)}
          >
            <t.Icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {target === 'dataapi' ? <DataApiPanel /> : <ConsolePanel />}
    </div>
  )
}
