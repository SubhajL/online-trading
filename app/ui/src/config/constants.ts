export function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3000/api'
}

export function getWebSocketUrl(): string {
  return process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3000'
}

export const TIMEFRAMES = [
  '1m',
  '3m',
  '5m',
  '15m',
  '30m',
  '1h',
  '2h',
  '4h',
  '6h',
  '8h',
  '12h',
  '1d',
  '3d',
  '1w',
  '1M',
] as const

export const RECONNECT_INTERVAL = 3000
export const MAX_RECONNECT_ATTEMPTS = 10
export const REQUEST_TIMEOUT = 30000
