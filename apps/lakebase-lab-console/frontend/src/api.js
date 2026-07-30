const BASE = '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  return res.json();
}

export const api = {
  // Identity & config
  whoami: () => request('/api/whoami'),
  health: () => request('/api/health'),
  config: () => request('/api/config'),
  dbtest: () => request('/api/dbtest'),

  // Branches
  listBranches: () => request('/api/branches'),
  getBranch: (id) => request(`/api/branches/${id}`),
  createBranch: (data) => request('/api/branches', { method: 'POST', body: JSON.stringify(data) }),
  deleteBranch: (id) => request(`/api/branches/${id}`, { method: 'DELETE' }),

  // Compute
  listEndpoints: (branchId) => request(`/api/compute/${branchId}`),
  computeTopology: (branchId) => request(`/api/compute/topology/${branchId}`),
  updateCompute: (branchId, endpointId, data) =>
    request(`/api/compute/${branchId}/${endpointId}`, { method: 'PATCH', body: JSON.stringify(data) }),

  // Load test
  startLoadTest: (data) => request('/api/loadtest/start', { method: 'POST', body: JSON.stringify(data) }),
  stopLoadTest: (id) => request(`/api/loadtest/stop/${id}`, { method: 'POST' }),
  loadTestStatus: (id) => request(`/api/loadtest/status/${id}`),
  activeLoadTest: () => request('/api/loadtest/active'),

  // Data
  listProducts: (cat) => request(`/api/data/products${cat ? `?category=${cat}` : ''}`),
  getProduct: (id) => request(`/api/data/products/${id}`),
  createProduct: (data) => request('/api/data/products', { method: 'POST', body: JSON.stringify(data) }),
  updateProduct: (id, data) => request(`/api/data/products/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProduct: (id) => request(`/api/data/products/${id}`, { method: 'DELETE' }),
  listEvents: (type) => request(`/api/data/events${type ? `?event_type=${type}` : ''}`),
  createEvent: (data) => request('/api/data/events', { method: 'POST', body: JSON.stringify(data) }),
  clearLoadtestEvents: () => request('/api/data/events/loadtest', { method: 'DELETE' }),
  listAudit: (table) => request(`/api/data/audit${table ? `?table_name=${table}` : ''}`),
  tableStats: () => request('/api/data/stats'),
  runQuery: (sql) => request('/api/data/query', { method: 'POST', body: JSON.stringify({ sql }) }),

  // Agent memory — short-term (sessions/messages)
  listSessions: () => request('/api/agent/sessions'),
  createSession: (data) => request('/api/agent/sessions', { method: 'POST', body: JSON.stringify(data) }),
  deleteSession: (id) => request(`/api/agent/sessions/${id}`, { method: 'DELETE' }),
  getMessages: (id) => request(`/api/agent/sessions/${id}/messages`),
  appendMessage: (id, data) =>
    request(`/api/agent/sessions/${id}/messages`, { method: 'POST', body: JSON.stringify(data) }),

  // Agent memory — long-term (memory store)
  listMemories: (userId) => request(`/api/agent/memories${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`),
  upsertMemory: (data) => request('/api/agent/memories', { method: 'POST', body: JSON.stringify(data) }),
  deleteMemory: (id) => request(`/api/agent/memories/${id}`, { method: 'DELETE' }),
  listMemoryUsers: () => request('/api/agent/memories/users'),

  // Observability
  obsDatabaseStats: () => request('/api/observability/database'),
  obsTableStats: () => request('/api/observability/tables'),
  obsIndexStats: () => request('/api/observability/indexes'),
  obsTableSizes: () => request('/api/observability/sizes'),
  obsConnections: () => request('/api/observability/connections'),
  obsActivity: () => request('/api/observability/activity'),
  obsStatements: () => request('/api/observability/statements'),

  // Online Tables / Feature Store / Synced Tables
  listOnlineStores: (mineOnly = true) => request(`/api/online-tables/stores?mine_only=${mineOnly}`),
  listSyncedTables: () => request('/api/online-tables/synced-tables'),
  listFeatureSpecs: () => request('/api/online-tables/feature-specs'),
  triggerSync: (tableId, pipelineId) =>
    request(`/api/online-tables/synced-tables/${tableId}/trigger?pipeline_id=${encodeURIComponent(pipelineId)}`, { method: 'POST' }),

  // Auth & Permissions
  authCredential: () => request('/api/auth/credential'),
  authRoles: () => request('/api/auth/roles'),
  authGrants: () => request('/api/auth/grants'),
  authConnectionInfo: () => request('/api/auth/connection-info'),
  authTls: () => request('/api/auth/tls'),

  // Data API (PostgREST)
  dataApiStatus: () => request('/api/data-api/status'),
  dataApiPrepare: () => request('/api/data-api/prepare', { method: 'POST' }),
  dataApiCall: (data) => request('/api/data-api/call', { method: 'POST', body: JSON.stringify(data) }),

  // Lakebase Search
  searchStatus: () => request('/api/search/status'),
  searchSeed: () => request('/api/search/seed', { method: 'POST' }),
  searchQuery: (data) => request('/api/search/query', { method: 'POST', body: JSON.stringify(data) }),

  // Generic (for API tester)
  raw: (method, path, body) =>
    request(path, { method, body: body ? JSON.stringify(body) : undefined }),
};
