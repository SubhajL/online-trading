import { test as base, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export type WebSocketFixtures = {
  mockWebSocket: MockWebSocket
}

export class MockWebSocket {
  private mockMessages: any[] = []
  private isConnected = false

  constructor(public readonly page: Page) {}

  async setup() {
    // Inject WebSocket mock into the page
    await this.page.addInitScript(() => {
      // Store original WebSocket
      const OriginalWebSocket = window.WebSocket

      // Create mock WebSocket class
      class MockWebSocket extends EventTarget {
        public readyState = WebSocket.CONNECTING
        public url: string
        public onopen: ((event: Event) => void) | null = null
        public onclose: ((event: CloseEvent) => void) | null = null
        public onmessage: ((event: MessageEvent) => void) | null = null
        public onerror: ((event: Event) => void) | null = null

        constructor(url: string) {
          super()
          this.url = url
          
          // Store reference for external control
          ;(window as any).__mockWebSocket = this
          
          // Simulate connection after a short delay
          setTimeout(() => {
            this.readyState = WebSocket.OPEN
            const openEvent = new Event('open')
            this.dispatchEvent(openEvent)
            if (this.onopen) this.onopen(openEvent)
          }, 100)
        }

        send(data: string) {
          console.log('MockWebSocket send:', data)
          // Store sent messages for verification
          ;(window as any).__sentMessages = (window as any).__sentMessages || []
          ;(window as any).__sentMessages.push(data)
        }

        close() {
          this.readyState = WebSocket.CLOSED
          const closeEvent = new CloseEvent('close')
          this.dispatchEvent(closeEvent)
          if (this.onclose) this.onclose(closeEvent)
        }

        // Method to simulate receiving messages
        simulateMessage(data: any) {
          const messageEvent = new MessageEvent('message', { data: JSON.stringify(data) })
          this.dispatchEvent(messageEvent)
          if (this.onmessage) this.onmessage(messageEvent)
        }
      }

      // Replace WebSocket with mock
      ;(window as any).WebSocket = MockWebSocket
      ;(window as any).__OriginalWebSocket = OriginalWebSocket
    })
  }

  async connect() {
    await this.setup()
    this.isConnected = true
  }

  async disconnect() {
    await this.page.evaluate(() => {
      const mockWS = (window as any).__mockWebSocket
      if (mockWS) {
        mockWS.close()
      }
    })
    this.isConnected = false
  }

  async sendMessage(data: any) {
    await this.page.evaluate((messageData) => {
      const mockWS = (window as any).__mockWebSocket
      if (mockWS) {
        mockWS.simulateMessage(messageData)
      }
    }, data)
  }

  async sendCandleUpdate(symbol: string, candle: any) {
    await this.sendMessage({
      type: 'candle',
      symbol,
      data: candle,
    })
  }

  async sendOrderUpdate(orderId: string, status: string, data: any = {}) {
    await this.sendMessage({
      type: 'order_update',
      orderId,
      status,
      data,
    })
  }

  async sendPositionUpdate(symbol: string, position: any) {
    await this.sendMessage({
      type: 'position',
      symbol,
      data: position,
    })
  }

  async sendPriceUpdate(symbol: string, price: number) {
    await this.sendMessage({
      type: 'price',
      symbol,
      price,
      timestamp: Date.now(),
    })
  }

  async sendBalanceUpdate(balance: any) {
    await this.sendMessage({
      type: 'balance',
      data: balance,
    })
  }

  async simulateDisconnection() {
    await this.page.evaluate(() => {
      const mockWS = (window as any).__mockWebSocket
      if (mockWS) {
        // Simulate network error
        const errorEvent = new Event('error')
        mockWS.dispatchEvent(errorEvent)
        if (mockWS.onerror) mockWS.onerror(errorEvent)
        
        // Then close
        mockWS.close()
      }
    })
  }

  async getSentMessages() {
    return await this.page.evaluate(() => {
      return (window as any).__sentMessages || []
    })
  }

  async clearSentMessages() {
    await this.page.evaluate(() => {
      ;(window as any).__sentMessages = []
    })
  }

  async expectMessageSent(expectedData: any) {
    const sentMessages = await this.getSentMessages()
    const found = sentMessages.some((msg: string) => {
      try {
        const parsed = JSON.parse(msg)
        return JSON.stringify(parsed) === JSON.stringify(expectedData)
      } catch {
        return msg === expectedData
      }
    })
    expect(found).toBe(true)
  }

  async expectConnectionStatus(connected: boolean) {
    const isConnected = await this.page.evaluate(() => {
      const mockWS = (window as any).__mockWebSocket
      return mockWS && mockWS.readyState === WebSocket.OPEN
    })
    expect(isConnected).toBe(connected)
  }
}

export const webSocketTest = base.extend<WebSocketFixtures>({
  mockWebSocket: async ({ page }, use) => {
    const mockWS = new MockWebSocket(page)
    await mockWS.connect()
    await use(mockWS)
    await mockWS.disconnect()
  },
})

export { expect } from '@playwright/test'
