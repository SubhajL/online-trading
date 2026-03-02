export type ApiEndpoints = {
  publicApiBase: string
  internalApiBase: string
  websocketBase: string
}

const DEFAULT_PUBLIC_API = 'http://localhost:3001/api'
const DEFAULT_INTERNAL_API = 'http://bff:3001/api'
const DEFAULT_WS = 'ws://localhost:3001'

function normalizeWebsocketBase(websocketBase: string): string {
  const trimmed = websocketBase.replace(/\/+$/, '')
  if (trimmed.endsWith('/trading')) return trimmed.slice(0, -'/trading'.length)
  if (trimmed.endsWith('/alerts')) return trimmed.slice(0, -'/alerts'.length)
  return trimmed
}

export function resolveApiEndpoints(): ApiEndpoints {
  const publicApiBase = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_PUBLIC_API
  const internalApiBase = process.env.NEXT_INTERNAL_API_URL ?? DEFAULT_INTERNAL_API
  const websocketBase = normalizeWebsocketBase(process.env.NEXT_PUBLIC_WS_URL ?? DEFAULT_WS)

  return { publicApiBase, internalApiBase, websocketBase }
}
