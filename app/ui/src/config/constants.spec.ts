import { describe, it, expect } from 'vitest'
import { getApiUrl, getWebSocketUrl, getAlertsWebSocketUrl } from './constants'

describe('getApiUrl', () => {
  it('returns API URL from environment variable when available', () => {
    const originalEnv = process.env.NEXT_PUBLIC_API_URL
    process.env.NEXT_PUBLIC_API_URL = 'https://api.production.com'

    expect(getApiUrl()).toBe('https://api.production.com')

    process.env.NEXT_PUBLIC_API_URL = originalEnv
  })

  it('returns default API URL when environment variable is not set', () => {
    const originalEnv = process.env.NEXT_PUBLIC_API_URL
    delete process.env.NEXT_PUBLIC_API_URL

    expect(getApiUrl()).toBe('http://localhost:3001/api')

    process.env.NEXT_PUBLIC_API_URL = originalEnv
  })
})

describe('getWebSocketUrl', () => {
  it('returns WebSocket URL from environment variable when available', () => {
    const originalEnv = process.env.NEXT_PUBLIC_WS_URL
    process.env.NEXT_PUBLIC_WS_URL = 'wss://ws.production.com'

    expect(getWebSocketUrl()).toBe('wss://ws.production.com/trading')

    process.env.NEXT_PUBLIC_WS_URL = originalEnv
  })

  it('returns default WebSocket URL when environment variable is not set', () => {
    const originalEnv = process.env.NEXT_PUBLIC_WS_URL
    delete process.env.NEXT_PUBLIC_WS_URL

    expect(getWebSocketUrl()).toBe('ws://localhost:3001/trading')

    process.env.NEXT_PUBLIC_WS_URL = originalEnv
  })

  it('accepts legacy NEXT_PUBLIC_WS_URL that includes /trading', () => {
    const originalEnv = process.env.NEXT_PUBLIC_WS_URL
    process.env.NEXT_PUBLIC_WS_URL = 'ws://localhost:3001/trading'

    expect(getWebSocketUrl()).toBe('ws://localhost:3001/trading')

    process.env.NEXT_PUBLIC_WS_URL = originalEnv
  })
})

describe('getAlertsWebSocketUrl', () => {
  it('returns alerts namespace URL from base', () => {
    const originalEnv = process.env.NEXT_PUBLIC_WS_URL
    process.env.NEXT_PUBLIC_WS_URL = 'wss://ws.production.com'

    expect(getAlertsWebSocketUrl()).toBe('wss://ws.production.com/alerts')

    process.env.NEXT_PUBLIC_WS_URL = originalEnv
  })

  it('accepts legacy NEXT_PUBLIC_WS_URL that includes /alerts', () => {
    const originalEnv = process.env.NEXT_PUBLIC_WS_URL
    process.env.NEXT_PUBLIC_WS_URL = 'ws://localhost:3001/alerts'

    expect(getAlertsWebSocketUrl()).toBe('ws://localhost:3001/alerts')

    process.env.NEXT_PUBLIC_WS_URL = originalEnv
  })
})
