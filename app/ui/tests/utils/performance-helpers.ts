import { Page, expect } from '@playwright/test'

export class PerformanceHelpers {
  constructor(private page: Page) {}

  async measurePageLoadTime(url: string): Promise<number> {
    const startTime = Date.now()
    await this.page.goto(url, { waitUntil: 'networkidle' })
    const endTime = Date.now()
    return endTime - startTime
  }

  async measureChartRenderTime(): Promise<number> {
    const startTime = Date.now()
    
    // Wait for chart container to be visible
    await this.page.waitForSelector('[data-testid="candlestick-chart"]', { state: 'visible' })
    
    // Wait for chart to be fully rendered (look for canvas or SVG elements)
    await this.page.waitForSelector('[data-testid="candlestick-chart"] canvas, [data-testid="candlestick-chart"] svg', { 
      state: 'visible' 
    })
    
    const endTime = Date.now()
    return endTime - startTime
  }

  async measureWebSocketLatency(): Promise<number> {
    // Inject performance measurement script
    await this.page.addInitScript(() => {
      ;(window as any).__wsLatencyStart = null
      ;(window as any).__wsLatencyEnd = null
      
      // Override WebSocket to measure latency
      const OriginalWebSocket = window.WebSocket
      ;(window as any).WebSocket = class extends OriginalWebSocket {
        constructor(url: string, protocols?: string | string[]) {
          super(url, protocols)
          
          this.addEventListener('open', () => {
            ;(window as any).__wsLatencyStart = performance.now()
            // Send a ping message
            this.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }))
          })
          
          this.addEventListener('message', (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.type === 'pong') {
                ;(window as any).__wsLatencyEnd = performance.now()
              }
            } catch (e) {
              // Ignore non-JSON messages
            }
          })
        }
      }
    })

    // Navigate to page that uses WebSocket
    await this.page.goto('/trading')
    
    // Wait for WebSocket connection and ping/pong
    await this.page.waitForFunction(() => {
      return (window as any).__wsLatencyEnd !== null
    }, { timeout: 10000 })

    // Get the measured latency
    const latency = await this.page.evaluate(() => {
      const start = (window as any).__wsLatencyStart
      const end = (window as any).__wsLatencyEnd
      return end - start
    })

    return latency
  }

  async measureOrderPlacementTime(orderData: any): Promise<number> {
    const startTime = performance.now()
    
    // Fill order form
    await this.page.fill('[data-testid="symbol-input"]', orderData.symbol)
    await this.page.selectOption('[data-testid="side-select"]', orderData.side)
    await this.page.selectOption('[data-testid="type-select"]', orderData.type)
    await this.page.fill('[data-testid="quantity-input"]', orderData.quantity)
    
    if (orderData.price) {
      await this.page.fill('[data-testid="price-input"]', orderData.price)
    }
    
    // Submit order and wait for response
    await this.page.click('[data-testid="place-order-btn"]')
    
    // Wait for order to appear in list or success message
    await this.page.waitForSelector('[data-testid="order-item"], [data-testid="order-success"]', {
      state: 'visible',
      timeout: 10000
    })
    
    const endTime = performance.now()
    return endTime - startTime
  }

  async measureTableRenderTime(tableSelector: string, expectedRows: number): Promise<number> {
    const startTime = performance.now()
    
    // Wait for table to have expected number of rows
    await this.page.waitForFunction(
      ({ selector, count }) => {
        const table = document.querySelector(selector)
        if (!table) return false
        const rows = table.querySelectorAll('tbody tr')
        return rows.length >= count
      },
      { selector: tableSelector, count: expectedRows },
      { timeout: 10000 }
    )
    
    const endTime = performance.now()
    return endTime - startTime
  }

  async measureMemoryUsage(): Promise<{ usedJSHeapSize: number; totalJSHeapSize: number }> {
    const memoryInfo = await this.page.evaluate(() => {
      return (performance as any).memory ? {
        usedJSHeapSize: (performance as any).memory.usedJSHeapSize,
        totalJSHeapSize: (performance as any).memory.totalJSHeapSize,
      } : { usedJSHeapSize: 0, totalJSHeapSize: 0 }
    })
    
    return memoryInfo
  }

  async measureFPS(durationMs: number = 5000): Promise<number> {
    const fps = await this.page.evaluate((duration) => {
      return new Promise<number>((resolve) => {
        let frameCount = 0
        const startTime = performance.now()
        
        function countFrame() {
          frameCount++
          const elapsed = performance.now() - startTime
          
          if (elapsed < duration) {
            requestAnimationFrame(countFrame)
          } else {
            const fps = (frameCount / elapsed) * 1000
            resolve(fps)
          }
        }
        
        requestAnimationFrame(countFrame)
      })
    }, durationMs)
    
    return fps
  }

  async expectPerformanceThreshold(measurement: number, threshold: number, metric: string) {
    expect(measurement, `${metric} should be under ${threshold}ms, but was ${measurement}ms`).toBeLessThan(threshold)
  }

  async expectFPSThreshold(fps: number, threshold: number) {
    expect(fps, `FPS should be above ${threshold}, but was ${fps.toFixed(2)}`).toBeGreaterThan(threshold)
  }

  async expectMemoryUsage(memoryMB: number, threshold: number) {
    expect(memoryMB, `Memory usage should be under ${threshold}MB, but was ${memoryMB.toFixed(2)}MB`).toBeLessThan(threshold)
  }

  // Web Vitals measurements
  async measureLCP(): Promise<number> {
    return await this.page.evaluate(() => {
      return new Promise<number>((resolve) => {
        new PerformanceObserver((list) => {
          const entries = list.getEntries()
          const lastEntry = entries[entries.length - 1]
          resolve(lastEntry.startTime)
        }).observe({ entryTypes: ['largest-contentful-paint'] })
        
        // Fallback timeout
        setTimeout(() => resolve(0), 10000)
      })
    })
  }

  async measureFID(): Promise<number> {
    return await this.page.evaluate(() => {
      return new Promise<number>((resolve) => {
        new PerformanceObserver((list) => {
          const entries = list.getEntries()
          if (entries.length > 0) {
            resolve(entries[0].processingStart - entries[0].startTime)
          }
        }).observe({ entryTypes: ['first-input'] })
        
        // Trigger a click to measure FID
        setTimeout(() => {
          const button = document.querySelector('button')
          if (button) {
            button.click()
          } else {
            resolve(0)
          }
        }, 1000)
        
        // Fallback timeout
        setTimeout(() => resolve(0), 10000)
      })
    })
  }

  async measureCLS(): Promise<number> {
    return await this.page.evaluate(() => {
      return new Promise<number>((resolve) => {
        let clsValue = 0
        
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (!(entry as any).hadRecentInput) {
              clsValue += (entry as any).value
            }
          }
        }).observe({ entryTypes: ['layout-shift'] })
        
        // Measure for 5 seconds
        setTimeout(() => resolve(clsValue), 5000)
      })
    })
  }
}
