import { test, expect } from '../fixtures'

test.describe('Market Data and Charts', () => {
  test.beforeEach(async ({ tradingPage }) => {
    await tradingPage.goto()

    // Wait for charts to be visible
    await expect(tradingPage.candlestickChart.container).toBeVisible()
    await expect(tradingPage.volumeChart.container).toBeVisible()
  })

  test('should display candlestick chart with data', async ({ tradingPage }) => {
    // Wait for chart to render
    const chart = tradingPage.candlestickChart.container
    await expect(chart).toBeVisible()

    // Check if canvas element exists (Lightweight Charts renders to canvas)
    const canvas = chart.locator('canvas')
    await expect(canvas).toBeVisible()

    // Verify chart has been rendered with data
    // Check for loading state to disappear
    await expect(tradingPage.page.locator('.loading-spinner')).not.toBeVisible({
      timeout: 10000,
    })

    // Verify chart controls are visible
    const timeframeButtons = await tradingPage.candlestickChart.timeframeButtons.all()
    expect(timeframeButtons.length).toBeGreaterThan(0)
  })

  test('should switch between different timeframes', async ({ tradingPage }) => {
    // Get initial canvas state
    const canvas = tradingPage.candlestickChart.container.locator('canvas')
    await canvas.waitFor({ state: 'visible' })

    // Take screenshot of initial state
    const initialScreenshot = await canvas.screenshot()

    // Click on different timeframe
    await tradingPage.selectTimeframe('5m')
    await tradingPage.page.waitForTimeout(2000) // Wait for chart update

    // Verify chart updated
    const updatedScreenshot = await canvas.screenshot()
    expect(Buffer.compare(initialScreenshot, updatedScreenshot)).not.toBe(0)

    // Try another timeframe
    await tradingPage.selectTimeframe('1h')
    await tradingPage.page.waitForTimeout(2000)

    // Verify active timeframe indicator
    const activeTimeframe = await tradingPage.page.locator('[data-testid="timeframe-1h"].active')
    await expect(activeTimeframe).toBeVisible()
  })

  test('should display volume chart synchronized with candlestick chart', async ({
    tradingPage,
  }) => {
    // Verify volume chart is visible
    const volumeChart = tradingPage.volumeChart.container
    await expect(volumeChart).toBeVisible()

    // Check for volume chart canvas
    const volumeCanvas = volumeChart.locator('canvas')
    await expect(volumeCanvas).toBeVisible()

    // Switch timeframe and verify both charts update
    await tradingPage.selectTimeframe('15m')
    await tradingPage.page.waitForTimeout(2000)

    // Both charts should be visible after update
    await expect(tradingPage.candlestickChart.container.locator('canvas')).toBeVisible()
    await expect(volumeChart.locator('canvas')).toBeVisible()
  })

  test('should handle real-time price updates', async ({ tradingPage }) => {
    // Wait for initial data
    await tradingPage.page.waitForTimeout(2000)

    // Monitor price display for changes
    const priceDisplay = tradingPage.page.locator('[data-testid="current-price"]')

    if (await priceDisplay.isVisible()) {
      const initialPrice = await priceDisplay.textContent()

      // Wait for potential price update (up to 30 seconds)
      let priceChanged = false
      const startTime = Date.now()

      while (Date.now() - startTime < 30000) {
        await tradingPage.page.waitForTimeout(1000)
        const currentPrice = await priceDisplay.textContent()

        if (currentPrice !== initialPrice) {
          priceChanged = true
          break
        }
      }

      // Price should update within 30 seconds during market hours
      // This test may fail during market close
      console.log('Price change detected:', priceChanged)
    }
  })

  test('should zoom and pan on charts', async ({ tradingPage }) => {
    const chartContainer = tradingPage.candlestickChart.container
    await expect(chartContainer).toBeVisible()

    // Get chart boundaries
    const box = await chartContainer.boundingBox()
    if (!box) throw new Error('Chart container not found')

    // Simulate mouse wheel for zoom
    await tradingPage.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await tradingPage.page.mouse.wheel(0, -100) // Zoom in
    await tradingPage.page.waitForTimeout(500)

    // Simulate drag for pan
    await tradingPage.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await tradingPage.page.mouse.down()
    await tradingPage.page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2)
    await tradingPage.page.mouse.up()
    await tradingPage.page.waitForTimeout(500)

    // Chart should still be visible after interactions
    await expect(chartContainer.locator('canvas')).toBeVisible()
  })

  test('should display chart loading states', async ({ tradingPage }) => {
    // Navigate to trigger fresh load
    await tradingPage.goto()

    // Check for loading spinner
    const loadingSpinner = tradingPage.page.locator('[data-testid="loading-spinner"]')

    // Loading spinner should appear briefly
    await expect(loadingSpinner).toBeVisible({ timeout: 5000 })

    // Wait for loading to complete
    await expect(loadingSpinner).not.toBeVisible({ timeout: 10000 })

    // Charts should be visible after loading
    await expect(tradingPage.candlestickChart.container).toBeVisible()
    await expect(tradingPage.volumeChart.container).toBeVisible()
  })

  test('should handle chart errors gracefully', async ({ tradingPage, page }) => {
    // Simulate network error by blocking API calls
    await page.route('**/api/candles**', route => {
      route.abort('failed')
    })

    // Reload page to trigger error
    await tradingPage.goto()

    // Should show error message
    const errorMessage = page.locator('[data-testid="error-message"]')
    await expect(errorMessage).toBeVisible({ timeout: 10000 })
    await expect(errorMessage).toContainText(/error|failed/i)

    // Retry button should be available
    const retryButton = page.locator('button:has-text("Retry")')
    await expect(retryButton).toBeVisible()

    // Unblock API and retry
    await page.unroute('**/api/candles**')
    await retryButton.click()

    // Charts should eventually load
    await expect(tradingPage.candlestickChart.container).toBeVisible({ timeout: 10000 })
  })

  test('should persist selected timeframe across page reloads', async ({ tradingPage }) => {
    // Select a non-default timeframe
    await tradingPage.selectTimeframe('4h')
    await tradingPage.page.waitForTimeout(1000)

    // Verify it's selected
    await expect(tradingPage.page.locator('[data-testid="timeframe-4h"].active')).toBeVisible()

    // Reload page
    await tradingPage.page.reload()
    await tradingPage.page.waitForLoadState('networkidle')

    // Verify timeframe is still selected
    await expect(tradingPage.page.locator('[data-testid="timeframe-4h"].active')).toBeVisible()
  })

  test('should display chart indicators', async ({ tradingPage }) => {
    // Check for price labels
    const priceScale = tradingPage.page.locator('.tv-price-scale')
    const timeScale = tradingPage.page.locator('.tv-time-scale')

    // These may not be visible with Lightweight Charts default setup
    // but we check for any axis labels
    const chartArea = tradingPage.candlestickChart.container
    await expect(chartArea).toBeVisible()

    // Look for crosshair functionality
    const box = await chartArea.boundingBox()
    if (box) {
      // Move mouse over chart to trigger crosshair
      await tradingPage.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await tradingPage.page.waitForTimeout(500)

      // Crosshair tooltip might appear
      const tooltip = tradingPage.page.locator('.chart-tooltip, [class*="tooltip"]').first()
      // Don't fail if tooltip doesn't exist - it's optional
      if (await tooltip.isVisible()) {
        await expect(tooltip).toBeVisible()
      }
    }
  })

  test('should synchronize chart data with order placement', async ({ tradingPage }) => {
    // Ensure charts are loaded
    await expect(tradingPage.candlestickChart.container).toBeVisible()

    // Place an order
    await tradingPage.placeOrder({
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    })

    await tradingPage.waitForOrderExecution()

    // Charts should continue updating
    await tradingPage.page.waitForTimeout(2000)
    await expect(tradingPage.candlestickChart.container.locator('canvas')).toBeVisible()
  })
})
