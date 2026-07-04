import { describe, it, expect, beforeEach, vi } from 'vitest'

const connectMock = vi.fn()
const disconnectMock = vi.fn()
const reconnectWithAuthMock = vi.fn()

vi.mock('./websocket.service', () => ({
  WebSocketService: class {
    connect = connectMock
    disconnect = disconnectMock
    reconnectWithAuth = reconnectWithAuthMock
  },
}))

vi.mock('@/config/constants', () => ({
  getWebSocketUrl: () => 'ws://localhost:3001/trading',
  getAlertsWebSocketUrl: () => 'ws://localhost:3001/alerts',
  getMarketDataWebSocketUrl: () => 'ws://localhost:3001/market-data',
}))

describe('websocket lifecycle module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not auto-connect on import', async () => {
    vi.resetModules()

    await import('./websocket')

    expect(connectMock).not.toHaveBeenCalled()
  })

  it('initWebsockets connects all namespaces and disconnectWebsockets closes all', async () => {
    vi.resetModules()
    const websocketModule = await import('./websocket')

    websocketModule.initWebsockets()
    expect(connectMock).toHaveBeenCalledTimes(3)
    expect(connectMock).toHaveBeenNthCalledWith(1, 'ws://localhost:3001/trading')
    expect(connectMock).toHaveBeenNthCalledWith(2, 'ws://localhost:3001/alerts')
    expect(connectMock).toHaveBeenNthCalledWith(3, 'ws://localhost:3001/market-data')

    websocketModule.disconnectWebsockets()
    expect(disconnectMock).toHaveBeenCalledTimes(3)
  })
})
