import { resolveApiEndpoints } from './runtime'

export function getApiUrl(): string {
  return resolveApiEndpoints().publicApiBase
}

export function getWebSocketUrl(): string {
  // BFF Socket.IO server namespace for trading/market-data + order operations
  const { websocketBase } = resolveApiEndpoints()
  return `${websocketBase}/trading`
}

export function getAlertsWebSocketUrl(): string {
  // BFF Socket.IO server namespace for realtime alerts
  const { websocketBase } = resolveApiEndpoints()
  return `${websocketBase}/alerts`
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
