import { useState, useEffect } from 'react'
import { api } from '../api'
import { Database, Plus, Trash2, RefreshCw, Check, Table, Clock, AlertCircle, Edit3, X, Search, Zap } from '../icons'
import LabBanner from '../LabBanner'

const DEFAULT_PRODUCTS = [
  { name: 'Wireless Mouse', price: 29.99, stock_quantity: 150, category: 'Electronics', description: 'Ergonomic wireless mouse with USB receiver', tags: ['wireless', 'ergonomic'] },
  { name: 'Mechanical Keyboard', price: 89.99, stock_quantity: 75, category: 'Electronics', description: 'RGB mechanical keyboard with Cherry MX switches', tags: ['mechanical', 'rgb', 'gaming'] },
  { name: 'Python Data Science Handbook', price: 49.95, stock_quantity: 200, category: 'Books', description: 'Essential tools for working with data in Python', tags: ['python', 'data-science'] },
  { name: 'USB-C Hub', price: 34.99, stock_quantity: 300, category: 'Accessories', description: '7-in-1 USB-C hub with HDMI and ethernet', tags: ['usb-c', 'hub', 'multiport'] },
  { name: 'Standing Desk Mat', price: 45.00, stock_quantity: 50, category: 'Office', description: 'Anti-fatigue mat for standing desks', tags: ['ergonomic', 'standing-desk'] },
]

const JSONB_QUERIES = [
  { label: 'Products with metadata', sql: "SELECT name, price, metadata FROM products WHERE metadata != '{}' LIMIT 10" },
  { label: 'Products by tag', sql: "SELECT name, price, tags FROM products WHERE 'wireless' = ANY(tags)" },
  { label: 'Category summary', sql: "SELECT category, count(*), round(avg(price)::numeric, 2) AS avg_price, sum(stock_quantity) AS total_stock FROM products GROUP BY category ORDER BY count DESC" },
  { label: 'Array overlap', sql: "SELECT name, tags FROM products WHERE tags && ARRAY['ergonomic', 'gaming'] LIMIT 10" },
  { label: 'Revenue estimate', sql: "SELECT name, price, stock_quantity, round((price * stock_quantity)::numeric, 2) AS potential_revenue FROM products ORDER BY potential_revenue DESC LIMIT 10" },
  { label: 'Audit summary', sql: "SELECT table_name, operation, count(*) AS cnt FROM audit_log GROUP BY table_name, operation ORDER BY cnt DESC" },
]

export default function DataPlayground() {
  const [tab, setTab] = useState('products')
  const [products, setProducts] = useState([])
  const [events, setEvents] = useState([])
  const [audit, setAudit] = useState([])
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [form, setForm] = useState({ name: '', price: '', stock_quantity: '', category: 'General', description: '', tags: '' })
  const [toast, setToast] = useState(null)
  const [queryResult, setQueryResult] = useState(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [customQuery, setCustomQuery] = useState('')
  const [eventForm, setEventForm] = useState({ event_type: 'user_action', source: 'lab-console', payload: '{"action": "click", "page": "home"}' })

  const loadProducts = () => {
    setLoading(true)
    api.listProducts().then(setProducts).finally(() => setLoading(false))
  }
  const loadEvents = () => api.listEvents().then(setEvents)
  const loadAudit = () => api.listAudit().then(setAudit)
  const loadStats = () => api.tableStats().then(setStats)

  useEffect(() => {
    loadProducts()
    loadAudit()
    loadStats()
  }, [])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleAdd = async (e) => {
    e.preventDefault()
    try {
      const tags = form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : []
      await api.createProduct({
        name: form.name,
        description: form.description,
        price: parseFloat(form.price),
        stock_quantity: parseInt(form.stock_quantity) || 0,
        category: form.category,
        tags,
      })
      showToast('Product created')
      setForm({ name: '', price: '', stock_quantity: '', category: 'General', description: '', tags: '' })
      setShowAdd(false)
      loadProducts(); loadAudit(); loadStats()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const fillDefault = (preset) => {
    setForm({
      name: preset.name,
      price: String(preset.price),
      stock_quantity: String(preset.stock_quantity),
      category: preset.category,
      description: preset.description || '',
      tags: (preset.tags || []).join(', '),
    })
    setShowAdd(true)
  }

  const handleEdit = (p) => {
    setEditingId(p.product_id)
    setEditForm({ name: p.name, price: p.price, stock_quantity: p.stock_quantity, category: p.category })
  }

  const handleSaveEdit = async () => {
    try {
      await api.updateProduct(editingId, {
        name: editForm.name,
        price: parseFloat(editForm.price),
        stock_quantity: parseInt(editForm.stock_quantity),
        category: editForm.category,
      })
      showToast('Product updated')
      setEditingId(null)
      loadProducts(); loadAudit(); loadStats()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const handleDelete = async (id) => {
    try {
      await api.deleteProduct(id)
      showToast('Product deleted')
      loadProducts(); loadAudit(); loadStats()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const runQuery = async (sql) => {
    setQueryLoading(true)
    setQueryResult(null)
    try {
      const res = await api.runQuery(sql)
      setQueryResult({ data: res, error: null, sql })
    } catch (err) {
      setQueryResult({ data: null, error: err.message, sql })
    }
    setQueryLoading(false)
  }

  const handleCreateEvent = async (e) => {
    e.preventDefault()
    try {
      let payload = {}
      try { payload = JSON.parse(eventForm.payload) } catch { payload = { raw: eventForm.payload } }
      await api.createEvent({ event_type: eventForm.event_type, source: eventForm.source, payload })
      showToast('Event created')
      loadEvents(); loadAudit(); loadStats()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>Data Operations Lab</h2>
        <p>
          Full CRUD on PostgreSQL tables with audit triggers. Add products with defaults or
          custom values, edit inline, run JSONB/array queries, and manage events.
        </p>
      </div>
      <LabBanner pageId="data" />

      <div className="metrics-row">
        {Object.entries(stats).map(([table, count]) => (
          <div className="metric-card" key={table}>
            <div className="metric-icon"><Table size={16} /></div>
            <div className="metric-value">{count >= 0 ? count.toLocaleString() : 'err'}</div>
            <div className="metric-label">{table}</div>
          </div>
        ))}
      </div>

      <div className="tab-group">
        <button className={`tab-btn ${tab === 'products' ? 'active' : ''}`} onClick={() => setTab('products')}>
          Products
        </button>
        <button className={`tab-btn ${tab === 'events' ? 'active' : ''}`} onClick={() => { setTab('events'); loadEvents() }}>
          Events
        </button>
        <button className={`tab-btn ${tab === 'queries' ? 'active' : ''}`} onClick={() => setTab('queries')}>
          SQL Queries
        </button>
        <button className={`tab-btn ${tab === 'audit' ? 'active' : ''}`} onClick={() => { setTab('audit'); loadAudit() }}>
          Audit Log
        </button>
      </div>

      {/* ── Products Tab ── */}
      {tab === 'products' && (
        <>
          <div className="card">
            <div className="card-header">
              <h3><Database size={16} /> Products ({products.length})</h3>
              <div className="btn-row">
                <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(!showAdd)}>
                  <Plus size={14} /> Add Product
                </button>
                <button className="btn btn-secondary btn-sm btn-icon" onClick={loadProducts}>
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>

            {showAdd && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 12 }}>
                  <div className="section-subheader">
                    Quick Fill from Examples
                  </div>
                  <div className="btn-row" style={{ flexWrap: 'wrap' }}>
                    {DEFAULT_PRODUCTS.map((p, i) => (
                      <button key={i} className="btn btn-secondary btn-xs" onClick={() => fillDefault(p)}>
                        <Zap size={11} /> {p.name}
                      </button>
                    ))}
                  </div>
                </div>
                <form onSubmit={handleAdd} className="form-inset">
                  <div className="form-row">
                    <div className="form-group">
                      <label>Name</label>
                      <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="Product name" />
                    </div>
                    <div className="form-group">
                      <label>Category</label>
                      <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                        <option>Electronics</option><option>Books</option><option>Accessories</option>
                        <option>Office</option><option>General</option>
                      </select>
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Price</label>
                      <input type="number" step="0.01" min="0" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} required placeholder="0.00" />
                    </div>
                    <div className="form-group">
                      <label>Stock Quantity</label>
                      <input type="number" min="0" value={form.stock_quantity} onChange={(e) => setForm({ ...form, stock_quantity: e.target.value })} placeholder="0" />
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Tags (comma separated)</label>
                    <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="wireless, ergonomic, gaming" />
                  </div>
                  <div className="form-group">
                    <label>Description</label>
                    <textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional description" />
                  </div>
                  <div className="btn-row">
                    <button className="btn btn-primary"><Check size={14} /> Save Product</button>
                    <button type="button" className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
                  </div>
                </form>
              </div>
            )}

            {loading ? (
              <div className="empty-state empty-state-compact"><p>Loading...</p></div>
            ) : products.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon"><Database size={36} /></div>
                <p>No products found. Add one using the defaults above.</p>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th><th>Name</th><th>Price</th><th>Stock</th><th>Category</th><th>Tags</th><th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((p) => (
                    <tr key={p.product_id}>
                      {editingId === p.product_id ? (
                        <>
                          <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{p.product_id}</td>
                          <td><input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} className="form-select" style={{ width: '100%', borderColor: 'var(--border-accent)' }} /></td>
                          <td><input type="number" step="0.01" value={editForm.price} onChange={(e) => setEditForm({ ...editForm, price: e.target.value })} className="form-select td-mono" style={{ width: 90, borderColor: 'var(--border-accent)' }} /></td>
                          <td><input type="number" value={editForm.stock_quantity} onChange={(e) => setEditForm({ ...editForm, stock_quantity: e.target.value })} className="form-select td-mono" style={{ width: 70, borderColor: 'var(--border-accent)' }} /></td>
                          <td>
                            <select value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })} className="form-select" style={{ borderColor: 'var(--border-accent)', fontSize: 12 }}>
                              <option>Electronics</option><option>Books</option><option>Accessories</option><option>Office</option><option>General</option>
                            </select>
                          </td>
                          <td></td>
                          <td style={{ textAlign: 'right' }}>
                            <div className="btn-row" style={{ justifyContent: 'flex-end' }}>
                              <button className="btn btn-primary btn-xs" onClick={handleSaveEdit}><Check size={12} /> Save</button>
                              <button className="btn btn-secondary btn-xs" onClick={() => setEditingId(null)}><X size={12} /></button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{p.product_id}</td>
                          <td style={{ fontWeight: 600 }}>{p.name}</td>
                          <td className="td-mono">${parseFloat(p.price).toFixed(2)}</td>
                          <td>
                            <span className={`badge ${p.stock_quantity > 50 ? 'badge-success' : p.stock_quantity > 0 ? 'badge-warning' : 'badge-danger'}`}>
                              {p.stock_quantity}
                            </span>
                          </td>
                          <td><span className="badge badge-purple">{p.category}</span></td>
                          <td>
                            {p.tags && p.tags.length > 0 && (
                              <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                                {p.tags.slice(0, 3).map((t, i) => (
                                  <span key={i} className="badge badge-cyan" style={{ fontSize: 10 }}>{t}</span>
                                ))}
                                {p.tags.length > 3 && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>+{p.tags.length - 3}</span>}
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <div className="btn-row" style={{ justifyContent: 'flex-end' }}>
                              <button className="btn btn-secondary btn-xs" onClick={() => handleEdit(p)}>
                                <Edit3 size={12} /> Edit
                              </button>
                              <button className="btn btn-danger btn-xs" onClick={() => handleDelete(p.product_id)}>
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* ── Events Tab ── */}
      {tab === 'events' && (
        <>
          <div className="card">
            <div className="card-header">
              <h3><Zap size={16} /> Create Event</h3>
            </div>
            <form onSubmit={handleCreateEvent}>
              <div className="form-row">
                <div className="form-group">
                  <label>Event Type</label>
                  <input value={eventForm.event_type} onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })} placeholder="user_action" />
                </div>
                <div className="form-group">
                  <label>Source</label>
                  <input value={eventForm.source} onChange={(e) => setEventForm({ ...eventForm, source: e.target.value })} placeholder="lab-console" />
                </div>
              </div>
              <div className="form-group">
                <label>Payload (JSON)</label>
                <textarea rows={3} value={eventForm.payload} onChange={(e) => setEventForm({ ...eventForm, payload: e.target.value })} className="td-mono-sm" />
              </div>
              <div className="btn-row">
                <button className="btn btn-primary btn-sm"><Plus size={14} /> Create Event</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => api.clearLoadtestEvents().then(() => { showToast('Load test events cleared'); loadEvents(); loadStats() })}>
                  <Trash2 size={14} /> Clear Load Test Events
                </button>
              </div>
            </form>
          </div>

          <div className="card">
            <div className="card-header">
              <h3><Database size={16} /> Recent Events ({events.length})</h3>
              <button className="btn btn-secondary btn-sm btn-icon" onClick={loadEvents}><RefreshCw size={14} /></button>
            </div>
            {events.length === 0 ? (
              <div className="empty-state empty-state-compact"><p>No events yet</p></div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr><th>ID</th><th>Type</th><th>Source</th><th>Payload</th><th>Created</th></tr>
                </thead>
                <tbody>
                  {events.slice(0, 50).map((e) => (
                    <tr key={e.event_id}>
                      <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{e.event_id}</td>
                      <td><span className="badge badge-info">{e.event_type}</span></td>
                      <td className="td-mono-sm">{e.source}</td>
                      <td className="td-mono-xs" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {typeof e.payload === 'object' ? JSON.stringify(e.payload) : e.payload}
                      </td>
                      <td className="td-mono-sm" style={{ color: 'var(--text-secondary)' }}>{e.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* ── SQL Queries Tab ── */}
      {tab === 'queries' && (
        <>
          <div className="card">
            <div className="card-header">
              <h3><Search size={16} /> JSONB & Array Query Examples</h3>
            </div>
            <div className="btn-row" style={{ flexWrap: 'wrap', marginBottom: 16 }}>
              {JSONB_QUERIES.map((q, i) => (
                <button key={i} className="btn btn-secondary btn-sm" onClick={() => { setCustomQuery(q.sql); runQuery(q.sql) }}>
                  <Zap size={12} /> {q.label}
                </button>
              ))}
            </div>
            <div className="form-group">
              <label>Custom SQL Query</label>
              <textarea rows={4} value={customQuery} onChange={(e) => setCustomQuery(e.target.value)} placeholder="SELECT * FROM products WHERE ..." className="td-mono-sm" />
            </div>
            <button className="btn btn-primary btn-sm" onClick={() => runQuery(customQuery)} disabled={queryLoading || !customQuery.trim()}>
              {queryLoading ? 'Running...' : <><Search size={14} /> Run Query</>}
            </button>
          </div>

          {queryResult && (
            <div className="card">
              <div className="card-header">
                <h3>{queryResult.error ? <AlertCircle size={16} style={{ color: 'var(--danger)' }} /> : <Check size={16} style={{ color: 'var(--success)' }} />} Results</h3>
                {queryResult.data && <span className="badge badge-info">{queryResult.data.length} rows</span>}
              </div>
              {queryResult.error ? (
                <div className="api-response error">{queryResult.error}</div>
              ) : queryResult.data && queryResult.data.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        {Object.keys(queryResult.data[0]).map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {queryResult.data.slice(0, 50).map((row, i) => (
                        <tr key={i}>
                          {Object.values(row).map((val, j) => (
                            <td key={j} className="td-mono-sm">
                              {val === null ? <span style={{ color: 'var(--text-muted)' }}>NULL</span> : typeof val === 'object' ? JSON.stringify(val) : String(val)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state empty-state-compact"><p>Query returned no rows</p></div>
              )}
              <div className="code-block" style={{ marginTop: 12, fontSize: 11 }}>{queryResult.sql}</div>
            </div>
          )}
        </>
      )}

      {/* ── Audit Tab ── */}
      {tab === 'audit' && (
        <div className="card">
          <div className="card-header">
            <h3><Clock size={16} /> Audit Log (last 50)</h3>
            <button className="btn btn-secondary btn-sm btn-icon" onClick={loadAudit}>
              <RefreshCw size={14} />
            </button>
          </div>
          {audit.length === 0 ? (
            <div className="empty-state empty-state-compact"><p>No audit entries yet. Create, edit, or delete a product to generate entries.</p></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>ID</th><th>Table</th><th>Operation</th><th>Record ID</th><th>Time</th></tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                    <tr key={a.audit_id}>
                      <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{a.audit_id}</td>
                      <td className="td-mono">{a.table_name}</td>
                    <td>
                      <span className={`badge ${a.operation === 'INSERT' ? 'badge-success' : a.operation === 'DELETE' ? 'badge-danger' : 'badge-warning'}`}>
                        {a.operation}
                      </span>
                    </td>
                    <td className="td-mono">{a.record_id}</td>
                    <td className="td-mono-sm" style={{ color: 'var(--text-secondary)' }}>{a.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {toast && (
        <div className={`toast toast-${toast.type}`}>
          {toast.type === 'success' ? <Check size={16} /> : <AlertCircle size={16} />}
          {toast.msg}
        </div>
      )}
    </div>
  )
}
