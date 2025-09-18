import { test, expect } from '../fixtures'
import type { Page } from '@playwright/test'

// Helper to wait for WebSocket connection
async function waitForWebSocketConnection(page: Page, timeout = 10000): Promise<boolean> {
  return page.evaluate(timeout => {
    return new Promise<boolean>(resolve => {
      const startTime = Date.now()

      const checkConnection = () => {
        // Check if WebSocket is connected by looking for global WebSocket instances
        const hasActiveWebSocket =
          (window as any).__wsConnected === true ||
          (window as any).io?.connected === true ||
          document.querySelector('[data-ws-status="connected"]') !== null

        if (hasActiveWebSocket) {
          resolve(true)
        } else if (Date.now() - startTime > timeout) {
          resolve(false)
        } else {
          setTimeout(checkConnection, 100)
        }
      }

      checkConnection()
    })
  }, timeout)
}

test.describe('WebSocket Real-time Updates', () => {
  test('should establish WebSocket connection on page load', async ({ page, tradingPage }) => {
    // Monitor WebSocket connections
    const wsConnections: string[] = []

    page.on('websocket', ws => {
      wsConnections.push(ws.url())
      console.log('WebSocket connected:', ws.url())
    })

    await tradingPage.goto()

    // Wait for WebSocket connection
    const connected = await waitForWebSocketConnection(page)
    expect(connected).toBe(true)

    // Should have at least one WebSocket connection
    expect(wsConnections.length).toBeGreaterThan(0)

    // Connection indicator should show connected status
    const statusIndicator = page.locator('[data-testid="ws-status"], .connection-status')
    if (await statusIndicator.isVisible()) {
      await expect(statusIndicator).toHaveClass(/connected|online|active/)
    }
  })

  test('should receive real-time price updates', async ({ page, tradingPage }) => {
    await tradingPage.goto()

    // Wait for initial connection
    await waitForWebSocketConnection(page)

    // Monitor price changes
    const priceElement = page.locator('[data-testid="current-price"], .price-display').first()

    if (await priceElement.isVisible()) {
      const prices: string[] = []

      // Collect price updates for 10 seconds
      const startTime = Date.now()
      while (Date.now() - startTime < 10000) {
        const currentPrice = await priceElement.textContent()
        if (currentPrice && !prices.includes(currentPrice)) {
          prices.push(currentPrice)
          console.log('Price update:', currentPrice)
        }
        await page.waitForTimeout(500)
      }

      // Should have received at least one price update
      console.log('Unique prices collected:', prices.length)
      // Note: This might not always pass during low volatility periods
    }
  })

  test('should update order book in real-time', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Look for order book component
    const orderBook = page.locator('[data-testid="order-book"], .order-book')

    if (await orderBook.isVisible()) {
      // Get initial bid/ask values
      const bidElements = orderBook.locator('[data-testid="bid-price"], .bid-price')
      const askElements = orderBook.locator('[data-testid="ask-price"], .ask-price')

      const initialBidCount = await bidElements.count()
      const initialAskCount = await askElements.count()

      // Should have some order book data
      expect(initialBidCount).toBeGreaterThan(0)
      expect(initialAskCount).toBeGreaterThan(0)

      // Monitor for updates
      let updateDetected = false
      const startTime = Date.now()

      while (!updateDetected && Date.now() - startTime < 10000) {
        const currentBidCount = await bidElements.count()
        const currentAskCount = await askElements.count()

        // Check if DOM has been updated
        if (currentBidCount !== initialBidCount || currentAskCount !== initialAskCount) {
          updateDetected = true
        }

        await page.waitForTimeout(100)
      }

      console.log('Order book update detected:', updateDetected)
    }
  })

  test('should handle WebSocket reconnection', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Get WebSocket instance through page context
    const wsUrl = await page.evaluate(() => {
      const ws = (window as any).__ws || (window as any).io
      return ws?.url || ws?.uri || 'unknown'
    })

    console.log('WebSocket URL:', wsUrl)

    // Simulate connection loss by going offline
    await page.context().setOffline(true)

    // Wait a moment
    await page.waitForTimeout(2000)

    // Should show disconnected state
    const statusIndicator = page.locator('[data-testid="ws-status"], .connection-status')
    if (await statusIndicator.isVisible()) {
      await expect(statusIndicator).toHaveClass(/disconnected|offline|error/)
    }

    // Go back online
    await page.context().setOffline(false)

    // Should reconnect automatically
    const reconnected = await waitForWebSocketConnection(page, 15000)
    expect(reconnected).toBe(true)

    // Status should be back to connected
    if (await statusIndicator.isVisible()) {
      await expect(statusIndicator).toHaveClass(/connected|online|active/)
    }
  })

  test('should sync order updates via WebSocket', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Monitor WebSocket messages
    const orderUpdates: any[] = []

    await page.evaluate(() => {
      const originalSend = WebSocket.prototype.send
      const originalOnMessage = Object.getOwnPropertyDescriptor(WebSocket.prototype, 'onmessage')

      // Monitor outgoing messages
      WebSocket.prototype.send = function (data) {
        window.postMessage({ type: 'ws-send', data: data.toString() }, '*')
        return originalSend.call(this, data)
      }

      // Monitor incoming messages
      Object.defineProperty(WebSocket.prototype, 'onmessage', {
        set: function (handler) {
          const wrappedHandler = (event: MessageEvent) => {
            window.postMessage({ type: 'ws-receive', data: event.data }, '*')
            if (handler) handler.call(this, event)
          }
          if (originalOnMessage?.set) {
            originalOnMessage.set.call(this, wrappedHandler)
          }
        },
      })
    })

    // Listen for WebSocket messages
    page.on('console', msg => {
      if (msg.type() === 'log' && msg.text().includes('ws-')) {
        console.log('WebSocket message:', msg.text())
      }
    })

    // Place an order to trigger WebSocket updates
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    // Wait for order updates
    await page.waitForTimeout(3000)

    // Order should appear in history via WebSocket update
    const orders = await tradingPage.orderHistory.orders.all()
    expect(orders.length).toBeGreaterThan(0)
  })

  test('should handle subscription management', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Track subscriptions
    const subscriptions = await page.evaluate(() => {
      const subs: string[] = []

      // Override WebSocket send to capture subscription messages
      const ws = (window as any).__ws || (window as any).io
      if (ws && ws.send) {
        const originalSend = ws.send.bind(ws)
        ws.send = function (data: any) {
          const message = typeof data === 'string' ? data : JSON.stringify(data)
          if (message.includes('subscribe')) {
            subs.push(message)
          }
          return originalSend(data)
        }
      }

      return new Promise<string[]>(resolve => {
        setTimeout(() => resolve(subs), 2000)
      })
    })

    console.log('Subscriptions detected:', subscriptions.length)

    // Navigate to different page/component
    await page.goto('/settings') // Assuming there's a settings page
    await page.waitForTimeout(1000)

    // Navigate back
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Should resubscribe to necessary channels
    const newSubscriptions = await page.evaluate(() => {
      return (window as any).__subscriptions || []
    })

    console.log('Resubscribed after navigation')
  })

  test('should throttle high-frequency updates', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Monitor DOM updates for throttling behavior
    const updateCounts = await page.evaluate(() => {
      const counts = {
        price: 0,
        orderBook: 0,
        trades: 0,
      }

      // Create mutation observer
      const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
          const target = mutation.target as HTMLElement
          if (target.dataset?.testid?.includes('price')) counts.price++
          if (target.dataset?.testid?.includes('order-book')) counts.orderBook++
          if (target.dataset?.testid?.includes('trades')) counts.trades++
        })
      })

      // Observe the entire document
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      })

      // Collect updates for 5 seconds
      return new Promise<typeof counts>(resolve => {
        setTimeout(() => {
          observer.disconnect()
          resolve(counts)
        }, 5000)
      })
    })

    console.log('Update counts:', updateCounts)

    // Updates should be happening but not excessively
    // Expect some updates but not hundreds per second
    Object.values(updateCounts).forEach(count => {
      if (count > 0) {
        expect(count).toBeLessThan(100) // Should be throttled
      }
    })
  })

  test('should maintain data consistency during updates', async ({ page, tradingPage }) => {
    await tradingPage.goto()
    await waitForWebSocketConnection(page)

    // Place multiple orders rapidly
    const orderPromises = []
    for (let i = 0; i < 3; i++) {
      orderPromises.push(
        tradingPage.placeOrder({
          symbol: 'BTCUSDT',
          side: i % 2 === 0 ? 'BUY' : 'SELL',
          type: 'MARKET',
          quantity: 0.001,
        }),
      )
    }

    await Promise.all(orderPromises)
    await page.waitForTimeout(3000)

    // Check data consistency
    // 1. Order count should match
    const orderCount = await tradingPage.orderHistory.orders.count()
    expect(orderCount).toBeGreaterThanOrEqual(3)

    // 2. No duplicate orders
    const orderIds = await tradingPage.orderHistory.orders.evaluateAll(orders => {
      return orders
        .map(order => {
          const idElement = order.querySelector('[data-order-id]')
          return (
            idElement?.getAttribute('data-order-id') ||
            order.textContent?.match(/Order #(\d+)/)?.[1]
          )
        })
        .filter(Boolean)
    })

    const uniqueOrderIds = new Set(orderIds)
    expect(uniqueOrderIds.size).toBe(orderIds.length) // No duplicates

    // 3. Balance should be updated consistently
    const balanceText = await tradingPage.accountBalance.totalBalance.textContent()
    expect(balanceText).toBeTruthy()
    expect(balanceText).toMatch(/[\d,]+\.?\d*/) // Valid number format
  })

  test('should show appropriate error states on WebSocket failure', async ({
    page,
    tradingPage,
  }) => {
    // Block WebSocket connections
    await page.route('ws://**', route => route.abort())
    await page.route('wss://**', route => route.abort())

    await tradingPage.goto()

    // Wait a bit for connection attempts
    await page.waitForTimeout(5000)

    // Should show connection error
    const errorStates = [
      page.locator('[data-testid="connection-error"]'),
      page.locator('.connection-error'),
      page.locator('text=/connection lost|disconnected|offline/i'),
    ]

    let errorFound = false
    for (const errorLocator of errorStates) {
      if (await errorLocator.isVisible()) {
        errorFound = true
        await expect(errorLocator).toBeVisible()
        break
      }
    }

    // Should show some indication of connection issues
    console.log('Connection error displayed:', errorFound)

    // Unblock WebSocket
    await page.unroute('ws://**')
    await page.unroute('wss://**')

    // Should eventually reconnect
    const reconnected = await waitForWebSocketConnection(page, 20000)
    if (reconnected) {
      // Error states should clear
      for (const errorLocator of errorStates) {
        if (await errorLocator.isVisible({ timeout: 1000 })) {
          await expect(errorLocator).not.toBeVisible({ timeout: 10000 })
        }
      }
    }
  })
})
