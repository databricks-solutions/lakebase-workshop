import { describe, it, expect } from 'vitest'
import { isSafeApiPath, pickPrefilledDataApiUrl } from './apiSafety'

describe('isSafeApiPath', () => {
  it('accepts same-origin /api/ paths', () => {
    expect(isSafeApiPath('/api/health')).toBe(true)
    expect(isSafeApiPath('/api/data/products?category=General')).toBe(true)
  })

  it('rejects absolute URLs and other origins', () => {
    expect(isSafeApiPath('https://evil.example.com/api/health')).toBe(false)
    expect(isSafeApiPath('//evil.example.com/api')).toBe(false)
    expect(isSafeApiPath('http://localhost/api/health')).toBe(false)
  })

  it('rejects non-api and traversal paths', () => {
    expect(isSafeApiPath('/etc/passwd')).toBe(false)
    expect(isSafeApiPath('/api/../secret')).toBe(false)
    expect(isSafeApiPath('/api//double')).toBe(false)
    expect(isSafeApiPath('')).toBe(false)
    expect(isSafeApiPath(null)).toBe(false)
  })
})

describe('pickPrefilledDataApiUrl', () => {
  it('prefills the trusted server-resolved endpoint when input is empty', () => {
    expect(
      pickPrefilledDataApiUrl({ data_api_url: 'https://mine.databricks.com/data-api' }, '')
    ).toBe('https://mine.databricks.com/data-api')
  })

  it('keeps what the user already typed', () => {
    expect(
      pickPrefilledDataApiUrl({ data_api_url: 'https://mine.databricks.com/data-api' }, 'typed')
    ).toBe('typed')
  })

  it('returns empty string when nothing is available', () => {
    expect(pickPrefilledDataApiUrl({}, '')).toBe('')
    expect(pickPrefilledDataApiUrl(null, '')).toBe('')
  })
})
