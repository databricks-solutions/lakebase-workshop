import { useState, useEffect } from 'react'
import { api } from '../api'
import {
  Search, RefreshCw, AlertCircle, Play, Sparkles, Database, Check,
} from '../icons'
import LabBanner from '../LabBanner'

const MODES = [
  { id: 'vector', label: 'Vector (semantic)' },
  { id: 'keyword', label: 'Keyword (BM25)' },
  { id: 'hybrid', label: 'Hybrid (RRF)' },
]

export default function SearchPage() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [seeding, setSeeding] = useState(false)

  const [mode, setMode] = useState('hybrid')
  const [text, setText] = useState('database search')
  const [vector, setVector] = useState('[0.11, 0.21, 0.32]')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)

  const loadStatus = async () => {
    setLoading(true)
    setError(null)
    try {
      setStatus(await api.searchStatus())
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => { loadStatus() }, [])

  const runSeed = async () => {
    setSeeding(true)
    setError(null)
    try {
      await api.searchSeed()
      await loadStatus()
    } catch (e) {
      setError(e.message)
    }
    setSeeding(false)
  }

  const runSearch = async () => {
    setSearching(true)
    setResults(null)
    setError(null)
    try {
      const r = await api.searchQuery({ mode, query: text, query_vector: vector, limit: 5 })
      setResults(r.results || [])
    } catch (e) {
      setError(e.message)
    }
    setSearching(false)
  }

  const ready = status?.ready
  const scoreKey = mode === 'vector' ? 'distance' : mode === 'keyword' ? 'score' : 'rrf_score'
  const scoreLabel = mode === 'vector' ? 'Distance' : mode === 'keyword' ? 'BM25 score' : 'RRF score'

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2>Lakebase Search <span className="badge badge-warning" style={{ verticalAlign: 'middle' }}>Beta</span></h2>
            <p>
              Hybrid vector + keyword search inside Postgres. Run semantic (<code>lakebase_vector</code>),
              keyword (<code>lakebase_text</code> / BM25), or fused hybrid ranking over a demo document set.
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={loadStatus} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'icon-spin' : ''} /> {loading ? 'Checking...' : 'Refresh'}
          </button>
        </div>
      </div>
      <LabBanner pageId="search" />

      {error && (
        <div className="alert-banner alert-banner-danger">
          <AlertCircle size={18} /><p>{error}</p>
        </div>
      )}

      {!ready ? (
        /* ── Informational fallback (Search not enabled) ── */
        <div className="card">
          <div className="card-header">
            <h3><Sparkles size={16} /> Lakebase Search isn't enabled yet</h3>
          </div>
          <div className="info-box danger">
            <span style={{ fontWeight: 600 }}>Enablement is irreversible:</span>
            <span>Enabling Lakebase Search restarts all computes in the project (dropping active connections) and <strong>cannot be turned off</strong>. It requires Beta access and Postgres 16+.</span>
          </div>
          <div className="info-box info" style={{ marginTop: 10 }}>
            <span style={{ fontWeight: 600 }}>How to enable:</span>
            <span>In your Lakebase project, open <strong>Settings -> Lakebase Search -> Enable</strong>, then install the extensions from the <code>labs/lakebase-search/</code> notebook. This app detects Search but never enables it for you.</span>
          </div>
          <table className="data-table" style={{ marginTop: 16 }}>
            <thead><tr><th>Capability</th><th>Extension</th><th>How it ranks</th></tr></thead>
            <tbody>
              <tr><td>Vector (semantic)</td><td className="td-mono-xs">lakebase_vector / lakebase_ann</td><td>Cosine distance <code>&lt;=&gt;</code> on embeddings</td></tr>
              <tr><td>Keyword</td><td className="td-mono-xs">lakebase_text / lakebase_bm25</td><td>BM25 relevance via <code>to_bm25query</code></td></tr>
              <tr><td>Hybrid</td><td className="td-mono-xs">both</td><td>Reciprocal Rank Fusion (RRF)</td></tr>
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {/* ── Status / seed ── */}
          <div className="card">
            <div className="card-header">
              <h3><Database size={16} /> Search Ready</h3>
              <div className="btn-row">
                <span className="badge badge-success"><Check size={11} /> Extensions installed</span>
                <span className={`badge ${status.table_exists ? 'badge-success' : 'badge-warning'}`}>
                  {status.table_exists ? 'Demo table ready' : 'Demo table missing'}
                </span>
              </div>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 12 }}>
              The <code>search_documents</code> demo table has 5 rows with a 3-dim embedding + a full-text
              column, plus <code>lakebase_ann</code> and <code>lakebase_bm25</code> indexes.
            </p>
            <button className="btn btn-primary btn-sm" onClick={runSeed} disabled={seeding}>
              <RefreshCw size={14} /> {seeding ? 'Building...' : status.table_exists ? 'Rebuild demo table' : 'Build demo table'}
            </button>
          </div>

          {/* ── Search ── */}
          <div className="card">
            <div className="card-header">
              <h3><Search size={16} /> Run a Search</h3>
            </div>
            <div className="btn-row" style={{ marginBottom: 12 }}>
              {MODES.map(m => (
                <button
                  key={m.id}
                  className={`btn btn-sm ${mode === m.id ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setMode(m.id); setResults(null) }}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {(mode === 'keyword' || mode === 'hybrid') && (
              <div className="form-group">
                <label>Keyword query</label>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="database search" />
              </div>
            )}
            {(mode === 'vector' || mode === 'hybrid') && (
              <div className="form-group">
                <label>Query vector (3-dim, matches the demo embeddings)</label>
                <input value={vector} onChange={(e) => setVector(e.target.value)} placeholder="[0.11, 0.21, 0.32]" className="td-mono-sm" />
              </div>
            )}
            <button className="btn btn-primary" onClick={runSearch} disabled={searching || !status.table_exists}>
              <Play size={14} /> {searching ? 'Searching...' : 'Search'}
            </button>
            {!status.table_exists && <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--text-muted)' }}>Build the demo table first.</span>}

            {results && (
              <table className="data-table" style={{ marginTop: 16 }}>
                <thead><tr><th>Rank</th><th>ID</th><th>Title</th><th style={{ textAlign: 'right' }}>{scoreLabel}</th></tr></thead>
                <tbody>
                  {results.length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No results</td></tr>
                  ) : results.map((r, i) => (
                    <tr key={r.id}>
                      <td>{i + 1}</td>
                      <td className="td-mono-xs">{r.id}</td>
                      <td>{r.title}</td>
                      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                        {typeof r[scoreKey] === 'number' ? r[scoreKey].toFixed(4) : String(r[scoreKey] ?? '--')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ── How it works ── */}
          <div className="card">
            <div className="card-header">
              <h3><Sparkles size={16} /> How Hybrid Search Works</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Vector:</span>
                <span>Orders by pgvector cosine distance <code>&lt;=&gt;</code> against the <code>lakebase_ann</code> index &mdash; nearest embeddings first.</span>
              </div>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Keyword:</span>
                <span><code>to_bm25query</code> against the <code>lakebase_bm25</code> index; the <code>&lt;@&gt;</code> operator returns a negative BM25 score, so lower is more relevant.</span>
              </div>
              <div className="info-box info">
                <span style={{ fontWeight: 600 }}>Hybrid (RRF):</span>
                <span>Rank each list independently, then fuse: <code>score = Σ 1 / (60 + rank)</code>. Rows ranking well in either list bubble to the top.</span>
              </div>
              <div className="info-box warning">
                <span style={{ fontWeight: 600 }}>Real embeddings:</span>
                <span>This demo uses hand-written 3-dim vectors. In production, embed text with Model Serving (<code>ai_query</code>) and match the <code>VECTOR(n)</code> dimension to the model's output. See Section 6 of the Lakebase Search lab.</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
