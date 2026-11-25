import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { Bot, Plus, Send, MessageSquare, X, Brain, Key, Search } from '../icons'
import LabBanner from '../LabBanner'

const TABS = [
  { id: 'short', label: 'Sessions (short-term)', Icon: MessageSquare },
  { id: 'long', label: 'Memory (long-term)', Icon: Brain },
]

function ShortTermPanel() {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [role, setRole] = useState('user')
  const [agentName, setAgentName] = useState('lab-agent')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const chatRef = useRef(null)

  const loadSessions = () => {
    api.listSessions()
      .then(setSessions)
      .catch((e) => setError(`Failed to load sessions: ${e.message}`))
  }

  useEffect(loadSessions, [])

  useEffect(() => {
    if (!activeSession) return
    api.getMessages(activeSession)
      .then(setMessages)
      .catch((e) => setError(`Failed to load messages: ${e.message}`))
  }, [activeSession])

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages])

  const createSession = async () => {
    setLoading(true)
    setError(null)
    try {
      const s = await api.createSession({ agent_name: agentName })
      loadSessions()
      setActiveSession(s.session_id)
    } catch (e) {
      setError(`Failed to create session: ${e.message}`)
    }
    setLoading(false)
  }

  const deleteSession = async (id) => {
    setError(null)
    try {
      await api.deleteSession(id)
      if (activeSession === id) { setActiveSession(null); setMessages([]) }
      loadSessions()
    } catch (e) {
      setError(`Failed to delete session: ${e.message}`)
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim() || !activeSession) return
    setError(null)
    try {
      await api.appendMessage(activeSession, { role, content: input })
      setInput('')
      api.getMessages(activeSession).then(setMessages)
    } catch (e) {
      setError(`Failed to send message: ${e.message}`)
    }
  }

  return (
    <div>
      {error && (
        <div className="info-box danger" style={{ marginBottom: 12 }}>
          <span>{error}</span>
          <button className="btn btn-xs" onClick={() => setError(null)} style={{ marginLeft: 'auto', padding: '2px 8px' }}>&times;</button>
        </div>
      )}
    <div className="grid-2col" style={{ gridTemplateColumns: '300px 1fr' }}>
      <div className="card" style={{ alignSelf: 'start' }}>
        <div className="card-header">
          <h3><Bot size={16} /> Sessions</h3>
        </div>
        <div className="form-group">
          <label>Agent Name</label>
          <input value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="lab-agent" />
        </div>
        <button className="btn btn-primary btn-sm" onClick={createSession} disabled={loading} style={{ marginBottom: 16, width: '100%' }}>
          <Plus size={14} /> New Session
        </button>

        {sessions.length === 0 ? (
          <div className="empty-state empty-state-compact">
            <div className="empty-icon"><MessageSquare size={24} /></div>
            <p>No sessions yet. Run the Agent Memory lab or create one.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sessions.map((s) => (
              <div
                key={s.session_id}
                className="list-item-card"
                style={{
                  padding: '10px 14px', cursor: 'pointer',
                  background: activeSession === s.session_id ? 'var(--accent-dim)' : undefined,
                  borderColor: activeSession === s.session_id ? 'var(--border-accent)' : undefined,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
                onClick={() => setActiveSession(s.session_id)}
              >
                <div>
                  <div className="td-mono-bold" style={{ fontSize: 12 }}>{s.session_id}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {s.agent_name || 'agent'} &middot; {(s.last_activity || s.created_at || '').replace('T', ' ').slice(0, 16)}
                  </div>
                </div>
                <button className="btn btn-danger btn-icon btn-xs"
                  onClick={(e) => { e.stopPropagation(); deleteSession(s.session_id) }}>
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        {!activeSession ? (
          <div className="empty-state">
            <div className="empty-icon"><MessageSquare size={36} /></div>
            <p>Select or create a session to replay its items</p>
          </div>
        ) : (
          <>
            <div className="card-header">
              <h3><MessageSquare size={16} /> Session: {activeSession}</h3>
              <span className="badge badge-info">{messages.length} items</span>
            </div>

            <div className="chat-messages" ref={chatRef}>
              {messages.length === 0 && (
                <div className="empty-state empty-state-compact"><p>No messages yet. Send one below.</p></div>
              )}
              {messages.map((m, i) => (
                <div key={m.item_id || i} className={`chat-msg ${m.role}`}>
                  <div className="msg-role">{m.role}</div>
                  {m.content}
                </div>
              ))}
            </div>

            <form onSubmit={sendMessage} style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <select value={role} onChange={(e) => setRole(e.target.value)}
                style={{ width: 110, padding: '8px 10px', background: 'var(--bg-inset)', border: '1px solid var(--border-light)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)' }}>
                <option value="user">user</option>
                <option value="assistant">assistant</option>
                <option value="system">system</option>
                <option value="tool">tool</option>
              </select>
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type a message..."
                style={{ flex: 1, padding: '8px 14px', background: 'var(--bg-inset)', border: '1px solid var(--border-light)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)', outline: 'none' }} />
              <button className="btn btn-primary" type="submit"><Send size={14} /> Send</button>
            </form>
          </>
        )}
      </div>
    </div>
    </div>
  )
}

function LongTermPanel() {
  const [memories, setMemories] = useState([])
  const [path, setPath] = useState('/preferences/')
  const [content, setContent] = useState('')
  const [description, setDescription] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadMemories = () => {
    api.listMemories()
      .then(setMemories)
      .catch((e) => setError(`Failed to load memories: ${e.message}`))
  }

  useEffect(loadMemories, [])

  const saveMemory = async (e) => {
    e.preventDefault()
    if (!path.trim() || !content.trim()) return
    setLoading(true)
    setError(null)
    try {
      await api.putMemory({ path, content, description: description || undefined })
      setContent('')
      setDescription('')
      // Leave search mode so the saved entry is visible in the full list.
      setResults(null)
      setQuery('')
      loadMemories()
    } catch (e) {
      setError(`Failed to save memory: ${e.message}`)
    }
    setLoading(false)
  }

  const deleteMemory = async (id) => {
    setError(null)
    try {
      await api.deleteMemory(id)
      setResults((r) => r && r.filter((m) => m.memory_id !== id))
      loadMemories()
    } catch (e) {
      setError(`Failed to delete memory: ${e.message}`)
    }
  }

  const search = async (e) => {
    e.preventDefault()
    if (!query.trim()) { setResults(null); return }
    setError(null)
    try {
      setResults(await api.searchMemories({ query, limit: 5 }))
    } catch (e) {
      setError(`Search failed: ${e.message}`)
    }
  }

  const shown = results ?? memories

  return (
    <div>
      {error && (
        <div className="info-box danger" style={{ marginBottom: 12 }}>
          <span>{error}</span>
          <button className="btn btn-xs" onClick={() => setError(null)} style={{ marginLeft: 'auto', padding: '2px 8px' }}>&times;</button>
        </div>
      )}
    <div className="grid-2col" style={{ gridTemplateColumns: '360px 1fr' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <h3><Plus size={16} /> Save Memory</h3>
          </div>
          <form onSubmit={saveMemory}>
            <div className="form-group">
              <label>Path</label>
              <input value={path} onChange={(e) => setPath(e.target.value)}
                placeholder="/preferences/response-style.md" />
            </div>
            <div className="form-group">
              <label>Content</label>
              <textarea value={content} onChange={(e) => setContent(e.target.value)}
                placeholder="Prefers concise answers with code samples."
                rows={3}
                style={{ width: '100%', padding: '8px 14px', background: 'var(--bg-inset)', border: '1px solid var(--border-light)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)', resize: 'vertical' }} />
            </div>
            <div className="form-group">
              <label>Description (improves retrieval)</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder="Response style" />
            </div>
            <button className="btn btn-primary btn-sm" type="submit" disabled={loading} style={{ width: '100%' }}>
              <Key size={14} /> Save (put)
            </button>
          </form>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
            Writing to an existing path replaces its content. Your email is the actor_id.
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3><Search size={16} /> Recall</h3>
          </div>
          <form onSubmit={search} style={{ display: 'flex', gap: 8 }}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="How should answers be formatted?"
              style={{ flex: 1, padding: '8px 14px', background: 'var(--bg-inset)', border: '1px solid var(--border-light)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)', outline: 'none' }} />
            <button className="btn btn-primary btn-sm" type="submit"><Search size={14} /></button>
          </form>
          {results && (
            <button className="btn btn-xs" style={{ marginTop: 8 }} onClick={() => { setResults(null); setQuery('') }}>
              Clear search
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3><Brain size={16} /> {results ? 'Search Results' : 'Memory Store'}</h3>
          <span className="badge badge-info">{shown.length} entries</span>
        </div>

        {shown.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><Brain size={36} /></div>
            <p>{results ? 'No matching memories.' : 'No memories yet. Run the Agent Memory lab or save one using the form.'}</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {shown.map((m) => (
              <div key={m.memory_id} className="list-item-card" style={{ padding: '12px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{m.path}</span>
                    {m.description && <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>{m.description}</span>}
                    {m.score != null && <span className="badge badge-info" style={{ marginLeft: 8 }}>score {m.score.toFixed(4)}</span>}
                  </div>
                  <button className="btn btn-danger btn-icon btn-xs" onClick={() => deleteMemory(m.memory_id)}>
                    <X size={12} />
                  </button>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
                  Updated: {m.updated_at}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
    </div>
  )
}

export default function AgentMemory() {
  const [tab, setTab] = useState('short')
  const [stores, setStores] = useState(null)

  useEffect(() => { api.agentStores().then(setStores).catch(() => {}) }, [])

  return (
    <div>
      <div className="page-header">
        <h2>Agent Memory</h2>
        <p>
          Managed agent memory backed by Lakebase: <strong>sessions</strong> hold one conversation's
          transcript, and <strong>memory</strong> holds durable facts recalled across conversations with
          natural-language search. A <strong>memory pipeline</strong> (run from the lab notebook) distills sessions into memory.
        </p>
        {stores && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Session store <code>{stores.session_store}</code> &middot; memory store <code>{stores.memory_store}</code> &middot; actor <code>{stores.actor_id}</code>
          </p>
        )}
      </div>
      <LabBanner pageId="agent" />

      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`btn btn-sm ${tab === t.id ? 'btn-primary' : ''}`}
            onClick={() => setTab(t.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <t.Icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'short' ? <ShortTermPanel /> : <LongTermPanel />}
    </div>
  )
}
