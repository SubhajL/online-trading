import { WebSocketService } from './websocket.service'
import { getWebSocketUrl } from '@/config/constants'

export type { ConnectionState } from './websocket.service'
export const websocketService = new WebSocketService()

// Initialize connection when the module is imported
if (typeof window !== 'undefined') {
  websocketService.connect(getWebSocketUrl())
}
