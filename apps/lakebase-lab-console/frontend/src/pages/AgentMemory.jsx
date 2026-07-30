import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { Bot, Plus, Trash2, Send, MessageSquare, X, Brain, Key } from '../icons'
import LabBanner from '../LabBanner'

const TABS = [
  { id: 'short', label: 'Short-term Memory', Icon: MessageSquare },
  { id: 'long', label: 'Long-term Memory', Icon: Brain },
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
    api.listSessions().then(setSessions).catch(() => {})
  }

  useEffect(loadSessions, [])

  useEffect(() => {
    if (!activeSession) return
    api.getMessages(activeSession).then(setMessages)
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
      setError(`Failed to create thread: ${e.message}`)
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
      setError(`Failed to delete thread: ${e.message}`)
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
          <h3><Bot size={16} /> Threads</h3>
        </div>
        <div className="form-group">
          <label>Agent Name</label>
          <input value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="lab-agent" />
        </div>
        <button className="btn btn-primary btn-sm" onClick={createSession} disabled={loading} style={{ marginBottom: 16, width: '100%' }}>
          <Plus size={14} /> New Thread
        </button>

        {sessions.length === 0 ? (
          <div className="empty-state empty-state-compact">
            <div className="empty-icon"><MessageSquare size={24} /></div>
            <p>No threads yet</p>
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
                    {s.agent_name} &middot; {s.message_count} msgs
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
            <p>Select or create a thread to view conversation history</p>
          </div>
        ) : (
          <>
            <div className="card-header">
              <h3><MessageSquare size={16} /> Thread: {activeSession}</h3>
              <span className="badge badge-info">{messages.length} messages</span>
            </div>

            <div className="chat-messages" ref={chatRef}>
              {messages.length === 0 && (
                <div className="empty-state empty-state-compact"><p>No messages yet. Send one below.</p></div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`chat-msg ${m.role}`}>
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
  const [users, setUsers] = useState([])
  const [filterUser, setFilterUser] = useState('')
  const [userId, setUserId] = useState('')
  const [topic, setTopic] = useState('')
  const [memory, setMemory] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadMemories = () => {
    api.listMemories(filterUser || undefined).then(setMemories).catch(() => {})
  }

  const loadUsers = () => {
    api.listMemoryUsers().then(setUsers).catch(() => {})
  }

  useEffect(() => { loadMemories(); loadUsers() }, [])
  useEffect(loadMemories, [filterUser])

  const saveMemory = async (e) => {
    e.preventDefault()
    if (!userId.trim() || !topic.trim() || !memory.trim()) return
    setLoading(true)
    setError(null)
    try {
      await api.upsertMemory({ user_id: userId, topic, memory })
      setTopic('')
      setMemory('')
      loadMemories()
      loadUsers()
    } catch (e) {
      setError(`Failed to save memory: ${e.message}`)
    }
    setLoading(false)
  }

  const deleteMemory = async (id) => {
    setError(null)
    try {
      await api.deleteMemory(id)
      loadMemories()
      loadUsers()
    } catch (e) {
      setError(`Failed to delete memory: ${e.message}`)
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
    <div className="grid-2col" style={{ gridTemplateColumns: '360px 1fr' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="card">
          <div className="card-header">
            <h3><Plus size={16} /> Store Memory</h3>
          </div>
          <form onSubmit={saveMemory}>
            <div className="form-group">
              <label>User ID</label>
              <input value={userId} onChange={(e) => setUserId(e.target.value)}
                placeholder="user@example.com" />
            </div>
            <div className="form-group">
              <label>Topic (key)</label>
              <input value={topic} onChange={(e) => setTopic(e.target.value)}
                placeholder="preferred_language" />
            </div>
            <div className="form-group">
              <label>Memory (value)</label>
              <textarea value={memory} onChange={(e) => setMemory(e.target.value)}
                placeholder="Python — user asked about data engineering"
                rows={3}
                style={{ width: '100%', padding: '8px 14px', background: 'var(--bg-inset)', border: '1px solid var(--border-light)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)', resize: 'vertical' }} />
            </div>
            <button className="btn btn-primary btn-sm" type="submit" disabled={loading} style={{ width: '100%' }}>
              <Key size={14} /> Save (Upsert)
            </button>
          </form>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
            Existing memories with the same user + topic are updated automatically.
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3><Bot size={16} /> Users</h3>
          </div>
          {users.length === 0 ? (
            <div style={{ padding: 12, fontSize: 13, color: 'var(--text-muted)' }}>No memories stored yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div
                className="list-item-card"
                style={{
                  padding: '8px 12px', cursor: 'pointer', fontSize: 13,
                  background: !filterUser ? 'var(--accent-dim)' : undefined,
                  borderColor: !filterUser ? 'var(--border-accent)' : undefined,
                }}
                onClick={() => setFilterUser('')}
              >All users</div>
              {users.map((u) => (
                <div
                  key={u.user_id}
                  className="list-item-card"
                  style={{
                    padding: '8px 12px', cursor: 'pointer',
                    background: filterUser === u.user_id ? 'var(--accent-dim)' : undefined,
                    borderColor: filterUser === u.user_id ? 'var(--border-accent)' : undefined,
                  }}
                  onClick={() => { setFilterUser(u.user_id); setUserId(u.user_id) }}
                >
                  <div className="td-mono-bold" style={{ fontSize: 12 }}>{u.user_id}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {u.memory_count} memories
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3><Brain size={16} /> Memory Store</h3>
          <span className="badge badge-info">{memories.length} memories</span>
        </div>

        {memories.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><Brain size={36} /></div>
            <p>No long-term memories stored yet. Add one using the form.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {memories.map((m) => (
              <div key={m.memory_id} className="list-item-card" style={{ padding: '12px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent)' }}>{m.topic}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>{m.user_id}</span>
                  </div>
                  <button className="btn btn-danger btn-icon btn-xs" onClick={() => deleteMemory(m.memory_id)}>
                    <X size={12} />
                  </button>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5 }}>{m.memory}</div>
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

  return (
    <div>
      <div className="page-header">
        <h2>Agent Memory</h2>
        <p>
          Explore both memory layers backed by Lakebase: <strong>short-term</strong> (thread-based
          conversations) and <strong>long-term</strong> (extracted key-value knowledge across sessions).
        </p>
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
