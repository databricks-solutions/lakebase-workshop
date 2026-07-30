import { useState, useEffect, createContext, useContext } from 'react'
import { api } from './api'
import {
  LayoutDashboard, TrendingUp, GitBranch, Cpu,
  Database, RefreshCw, Bot, Terminal, Layers, Sun, Moon, ExternalLink,
  Activity, Key, Shield, Server, Search
} from './icons'
import Dashboard from './pages/Dashboard'
import BranchManager from './pages/BranchManager'
import ComputePage from './pages/ComputePage'
import AutoscaleDemo from './pages/AutoscaleDemo'
import DataPlayground from './pages/DataPlayground'
import SyncStatus from './pages/SyncStatus'
import ApiTester from './pages/ApiTester'
import AgentMemory from './pages/AgentMemory'
import ObservabilityPage from './pages/ObservabilityPage'
import FeatureStorePage from './pages/FeatureStorePage'
import AuthPage from './pages/AuthPage'
import BackupRecoveryPage from './pages/BackupRecoveryPage'
import HighAvailabilityPage from './pages/HighAvailabilityPage'
import SearchPage from './pages/SearchPage'

export const AppContext = createContext(null)
export const useAppContext = () => useContext(AppContext)

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard, section: 'overview' },
  { id: 'autoscale', label: 'Autoscale Demo', Icon: TrendingUp, section: 'overview' },
  { id: 'data', label: 'Data Ops', Icon: Database, section: 'labs' },
  { id: 'search', label: 'Lakebase Search', Icon: Search, section: 'labs' },
  { id: 'observability', label: 'Observability', Icon: Activity, section: 'labs' },
  { id: 'sync', label: 'Synced Tables', Icon: RefreshCw, section: 'labs' },
  { id: 'feature-store', label: 'Feature Store', Icon: Layers, section: 'labs' },
  { id: 'agent', label: 'Agent Memory', Icon: Bot, section: 'labs' },
  { id: 'auth', label: 'Auth & Security', Icon: Key, section: 'labs' },
  { id: 'backup', label: 'Backup & Recovery', Icon: Shield, section: 'labs' },
  { id: 'branches', label: 'Branches', Icon: GitBranch, section: 'manage' },
  { id: 'compute', label: 'Compute', Icon: Cpu, section: 'manage' },
  { id: 'ha', label: 'High Availability', Icon: Server, section: 'manage' },
  { id: 'api', label: 'API Tester', Icon: Terminal, section: 'tools' },
]

const VALID_PAGES = new Set(NAV_ITEMS.map(i => i.id))

const SECTIONS = [
  { key: 'overview', label: 'Overview' },
  { key: 'labs', label: 'Labs' },
  { key: 'manage', label: 'Infrastructure' },
  { key: 'tools', label: 'Tools' },
]

function getInitialTheme() {
  const stored = localStorage.getItem('lakebase-theme')
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function formatUserDisplay(email) {
  if (!email) return ''
  const local = email.split('@')[0]
  return local.replace(/[._-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function getInitialPage() {
  const hash = window.location.hash.slice(1)
  return VALID_PAGES.has(hash) ? hash : 'dashboard'
}

export default function App() {
  const [activePage, setActivePage] = useState(getInitialPage)
  const [dbStatus, setDbStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [userInfo, setUserInfo] = useState(null)
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('lakebase-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))

  useEffect(() => {
    window.location.hash = activePage === 'dashboard' ? '' : activePage
  }, [activePage])

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1)
      if (VALID_PAGES.has(hash)) setActivePage(hash)
      else if (!hash) setActivePage('dashboard')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    api.whoami().then(setUserInfo).catch(() => {})
    api.dbtest().then(setDbStatus).catch(() => setDbStatus({ db_connected: false }))
    api.config().then(setConfig).catch(() => {})
  }, [])

  const renderPage = () => {
    switch (activePage) {
      case 'dashboard': return <Dashboard onNavigate={setActivePage} />
      case 'autoscale': return <AutoscaleDemo />
      case 'branches': return <BranchManager />
      case 'compute': return <ComputePage />
      case 'data': return <DataPlayground />
      case 'sync': return <SyncStatus config={config} />
      case 'api': return <ApiTester />
      case 'agent': return <AgentMemory />
      case 'observability': return <ObservabilityPage />
      case 'feature-store': return <FeatureStorePage />
      case 'auth': return <AuthPage />
      case 'backup': return <BackupRecoveryPage />
      case 'ha': return <HighAvailabilityPage />
      case 'search': return <SearchPage />
      default: return <Dashboard onNavigate={setActivePage} />
    }
  }

  const appCtx = { config, userInfo, onNavigate: setActivePage }

  return (
    <AppContext.Provider value={appCtx}>
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-row">
            <div className="sidebar-logo">
              <Layers size={18} />
            </div>
            <h1>Lakebase Lab</h1>
          </div>
          {userInfo?.email && (
            <p title={userInfo.email} style={{ fontSize: 12, opacity: 0.8 }}>
              {formatUserDisplay(userInfo.email)}
            </p>
          )}
          {(userInfo?.project_id || config?.project_id) && (
            <p className="td-mono-xs" style={{ opacity: 0.6 }}>
              {userInfo?.project_id || config?.project_id}
            </p>
          )}
        </div>
        <ul className="sidebar-nav">
          {SECTIONS.map((section) => {
            const items = NAV_ITEMS.filter((i) => i.section === section.key)
            if (items.length === 0) return null
            return (
              <li key={section.key}>
                <div className="sidebar-section-label">{section.label}</div>
                <ul>
                  {items.map((item) => (
                    <li key={item.id}>
                      <a
                        href="#"
                        className={activePage === item.id ? 'active' : ''}
                        onClick={(e) => { e.preventDefault(); setActivePage(item.id) }}
                      >
                        <span className="nav-icon"><item.Icon size={16} /></span>
                        <span>{item.label}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ul>
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className={`status-dot ${dbStatus?.db_connected ? 'connected' : 'disconnected'}`} />
            <span style={{ flex: 1 }}>{dbStatus?.db_connected ? 'Connected' : 'Disconnected'}</span>
            <button className="theme-toggle" onClick={toggleTheme} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
          {dbStatus?.db_connected && config?.workspace_host && config?.project_id && (
            <a
              className="lakebase-link"
              href={`${config.workspace_host}/lakebase/projects/${config.project_id}${config.branch_id ? `?branchId=${config.branch_id}` : ''}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Database size={14} />
              <span>Open in Lakebase</span>
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </aside>
      <main className="main-content">
        {renderPage()}
      </main>
    </div>
    </AppContext.Provider>
  )
}
