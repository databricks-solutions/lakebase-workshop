// Pure, testable helpers shared by the API Tester and Data API panel.

// The API Tester may only target the app's own same-origin API surface. This
// rejects absolute URLs, protocol-relative "//", parent traversal, and any path
// that does not start with /api/.
export function isSafeApiPath(p) {
  return (
    typeof p === 'string' &&
    /^\/api\/[A-Za-z0-9_./?=&%-]*$/.test(p) &&
    !p.includes('..') &&
    !p.includes('//')
  )
}

// Choose the Data API URL to display: prefer the server-resolved, trusted
// endpoint for the caller's own project; keep whatever the user already typed.
export function pickPrefilledDataApiUrl(status, currentUrl) {
  if (currentUrl) return currentUrl
  return status && status.data_api_url ? status.data_api_url : ''
}
