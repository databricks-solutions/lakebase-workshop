import { useAppContext } from './App'
import { BookOpen, ExternalLink } from './icons'

const NOTEBOOK_MAP = {
  'data':          { path: 'labs/data-operations/Data_Operations',                  label: 'Data Operations' },
  'observability': { path: 'labs/observability/Observability_and_Monitoring',        label: 'Observability & Monitoring' },
  'sync':          { path: 'labs/reverse-etl/Reverse_ETL',                           label: 'Synced Tables (Reverse ETL)' },
  'feature-store': { path: 'labs/online-feature-store/Online_Feature_Store',         label: 'Online Feature Store' },
  'agent':         { path: 'labs/agentic-memory/Agent_Memory',                       label: 'Agent Memory' },
  'auth':          { path: 'labs/authentication/Authentication_and_Permissions',     label: 'Authentication, Security & Compliance' },
  'backup':        { path: 'labs/backup-recovery/Backup_and_Recovery',               label: 'Backup & Recovery' },
  'branches':      { path: 'labs/development-experience/Branches_and_Environments',  label: 'Branches & Environments' },
  'compute':       { path: 'labs/development-experience/Autoscaling_and_Compute',    label: 'Autoscaling & Compute' },
  'autoscale':     { path: 'labs/development-experience/Autoscaling_and_Compute',    label: 'Autoscaling & Compute' },
  'ha':            { path: 'labs/development-experience/High_Availability_and_Replicas', label: 'High Availability & Replicas' },
  'search':        { path: 'labs/lakebase-search/Lakebase_Search',                   label: 'Lakebase Search' },
  'data-api':      { path: 'labs/data-api/Data_API',                                 label: 'Data API' },
}

export function getNotebookUrl(config, pageId) {
  const nb = NOTEBOOK_MAP[pageId]
  if (!nb || !config?.notebook_base_url) return null
  return `${config.notebook_base_url}/${nb.path}`
}

export default function LabBanner({ pageId }) {
  const ctx = useAppContext()
  const config = ctx?.config
  const nb = NOTEBOOK_MAP[pageId]
  if (!nb) return null

  const url = getNotebookUrl(config, pageId)

  return (
    <div className="lab-banner">
      <BookOpen size={15} />
      <span>
        This lab is also available as a <strong>notebook</strong> — run it step-by-step with full explanations.
      </span>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="lab-banner-link">
          Open {nb.label} Notebook <ExternalLink size={12} />
        </a>
      ) : (
        <span className="lab-banner-hint">Deploy the workshop bundle to access notebooks.</span>
      )}
    </div>
  )
}

export { NOTEBOOK_MAP }
