import { WebSocketService } from './websocket.service'
import { getAlertsWebSocketUrl, getWebSocketUrl } from '@/config/constants'

export type { ConnectionState } from './websocket.service'
export const tradingWebsocketService = new WebSocketService()
export const alertsWebsocketService = new WebSocketService()

// Back-compat: most of the UI expects a single trading socket
export const websocketService = tradingWebsocketService

export function reconnectAllWebsocketsWithAuth(): void {
  tradingWebsocketService.reconnectWithAuth()
  alertsWebsocketService.reconnectWithAuth()
}

export function initWebsockets(): void {
  if (typeof window === 'undefined') return
  tradingWebsocketService.connect(getWebSocketUrl())
  alertsWebsocketService.connect(getAlertsWebSocketUrl())
}

export function disconnectWebsockets(): void {
  tradingWebsocketService.disconnect()
  alertsWebsocketService.disconnect()
}
