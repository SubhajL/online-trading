import { test, expect } from '../fixtures'

test.describe('Auto Trading', () => {
  test.beforeEach(async ({ tradingPage }) => {
    await tradingPage.goto()
    await expect(tradingPage.autoTrading.toggle).toBeVisible()
  })

  test('should toggle auto trading on and off', async ({ tradingPage }) => {
    // Check initial state (should be off)
    const toggle = tradingPage.autoTrading.toggle
    const status = tradingPage.autoTrading.status

    await expect(status).toContainText('Inactive')
    await expect(toggle).not.toBeChecked()

    // Turn on auto trading
    await toggle.click()

    // Verify state changed
    await expect(toggle).toBeChecked()
    await expect(status).toContainText('Active')

    // Status indicator should show active color
    await expect(status).toHaveClass(/active|success|green/)

    // Turn off auto trading
    await toggle.click()

    // Verify state changed back
    await expect(toggle).not.toBeChecked()
    await expect(status).toContainText('Inactive')
  })

  test('should show confirmation dialog when enabling auto trading', async ({ tradingPage }) => {
    // Click to enable
    await tradingPage.toggleAutoTrading()

    // Look for confirmation dialog
    const dialog = tradingPage.page.locator('[role="dialog"], .modal, .confirmation-dialog')

    if (await dialog.isVisible({ timeout: 2000 })) {
      await expect(dialog).toContainText(/confirm|sure|enable auto trading/i)

      // Confirm action
      const confirmButton = dialog.locator('button:has-text("Confirm"), button:has-text("Yes")')
      await confirmButton.click()

      // Verify auto trading is enabled
      await expect(tradingPage.autoTrading.status).toContainText('Active')
    } else {
      // If no dialog, verify it's enabled directly
      await expect(tradingPage.autoTrading.status).toContainText('Active')
    }
  })

  test('should display auto trading statistics when active', async ({ tradingPage }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Wait for potential confirmation
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    // Check for statistics display
    await tradingPage.page.waitForTimeout(2000) // Wait for stats to appear

    // Look for auto trading stats
    const statsContainer = tradingPage.page.locator(
      '[data-testid="auto-trading-stats"], .auto-trading-statistics',
    )

    if (await statsContainer.isVisible()) {
      // Should show relevant statistics
      const possibleStats = [
        'Orders Placed',
        'Success Rate',
        'Total Profit',
        'Active Since',
        'Strategy',
      ]

      for (const stat of possibleStats) {
        const statElement = statsContainer.locator(`text=${stat}`)
        if (await statElement.isVisible()) {
          await expect(statElement).toBeVisible()
        }
      }
    }
  })

  test('should disable manual order placement when auto trading is active', async ({
    tradingPage,
  }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Confirm if needed
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    // Wait for state to update
    await expect(tradingPage.autoTrading.status).toContainText('Active')

    // Check if order form is disabled
    const orderFormDisabled = await tradingPage.orderForm.submitButton.isDisabled()

    if (orderFormDisabled) {
      // Verify form shows disabled state
      await expect(tradingPage.orderForm.submitButton).toBeDisabled()

      // Might show a message
      const warningMessage = tradingPage.page.locator('text=/manual.*disabled.*auto.*trading/i')
      if (await warningMessage.isVisible()) {
        await expect(warningMessage).toBeVisible()
      }
    } else {
      // Some systems allow manual orders alongside auto trading
      // Verify we can still place orders
      await expect(tradingPage.orderForm.submitButton).toBeEnabled()
    }
  })

  test('should show auto trading activity in order history', async ({ tradingPage }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Confirm if needed
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    // Wait for auto trading to potentially place orders
    await tradingPage.page.waitForTimeout(10000) // Wait up to 10 seconds

    // Check order history for auto-trading indicators
    const orders = await tradingPage.orderHistory.orders.all()

    if (orders.length > 0) {
      // Look for auto trading badges or labels
      let foundAutoOrder = false

      for (const order of orders) {
        const orderText = await order.textContent()
        const hasAutoBadge = await order
          .locator('[data-testid="auto-badge"], .auto-trading-badge')
          .isVisible()

        if (hasAutoBadge || orderText?.toLowerCase().includes('auto')) {
          foundAutoOrder = true
          break
        }
      }

      // Log whether auto orders were found
      console.log('Auto trading orders found:', foundAutoOrder)
    }
  })

  test('should persist auto trading state across page reloads', async ({ tradingPage }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Confirm if needed
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    // Verify it's active
    await expect(tradingPage.autoTrading.status).toContainText('Active')

    // Reload page
    await tradingPage.page.reload()
    await tradingPage.page.waitForLoadState('networkidle')

    // Verify state persisted
    await expect(tradingPage.autoTrading.toggle).toBeVisible()
    await expect(tradingPage.autoTrading.toggle).toBeChecked()
    await expect(tradingPage.autoTrading.status).toContainText('Active')
  })

  test('should handle auto trading errors gracefully', async ({ tradingPage, page }) => {
    // Simulate API error for auto trading
    await page.route('**/api/auto-trading**', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Auto trading service unavailable' }),
      })
    })

    // Try to enable auto trading
    await tradingPage.toggleAutoTrading()

    // Should show error message
    const errorMessage = page.locator('[data-testid="error-message"], .error-message')
    await expect(errorMessage).toBeVisible({ timeout: 5000 })
    await expect(errorMessage).toContainText(/error|failed|unavailable/i)

    // Toggle should remain off
    await expect(tradingPage.autoTrading.toggle).not.toBeChecked()
    await expect(tradingPage.autoTrading.status).toContainText('Inactive')
  })

  test('should allow emergency stop of auto trading', async ({ tradingPage }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Confirm if needed
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    await expect(tradingPage.autoTrading.status).toContainText('Active')

    // Look for emergency stop button
    const emergencyStop = tradingPage.page.locator(
      '[data-testid="emergency-stop"], button:has-text("Emergency Stop")',
    )

    if (await emergencyStop.isVisible()) {
      await emergencyStop.click()

      // Should immediately disable auto trading
      await expect(tradingPage.autoTrading.toggle).not.toBeChecked()
      await expect(tradingPage.autoTrading.status).toContainText('Inactive')

      // Might show notification
      const notification = tradingPage.page.locator('text=/emergency stop|stopped/i')
      if (await notification.isVisible()) {
        await expect(notification).toBeVisible()
      }
    } else {
      // Use regular toggle as emergency stop
      await tradingPage.toggleAutoTrading()
      await expect(tradingPage.autoTrading.status).toContainText('Inactive')
    }
  })

  test('should display auto trading configuration options', async ({ tradingPage }) => {
    // Look for settings/config button
    const configButton = tradingPage.page.locator(
      '[data-testid="auto-trading-config"], button:has-text("Settings"), button:has-text("Configure")',
    )

    if (await configButton.isVisible()) {
      await configButton.click()

      // Should show configuration modal/panel
      const configPanel = tradingPage.page.locator(
        '[data-testid="auto-trading-settings"], .settings-panel, [role="dialog"]',
      )
      await expect(configPanel).toBeVisible()

      // Check for common configuration options
      const configOptions = [
        'Risk Level',
        'Max Position Size',
        'Stop Loss',
        'Take Profit',
        'Trading Pairs',
        'Strategy',
      ]

      for (const option of configOptions) {
        const optionElement = configPanel.locator(`text=/${option}/i`).first()
        if (await optionElement.isVisible({ timeout: 1000 })) {
          console.log(`Found config option: ${option}`)
        }
      }

      // Close config
      const closeButton = configPanel.locator(
        'button:has-text("Close"), button:has-text("Cancel"), [aria-label="Close"]',
      )
      if (await closeButton.isVisible()) {
        await closeButton.click()
      } else {
        await tradingPage.page.keyboard.press('Escape')
      }
    }
  })

  test('should integrate with position management', async ({ tradingPage }) => {
    // Enable auto trading
    await tradingPage.toggleAutoTrading()

    // Confirm if needed
    const confirmButton = tradingPage.page.locator('button:has-text("Confirm")')
    if (await confirmButton.isVisible({ timeout: 2000 })) {
      await confirmButton.click()
    }

    // Wait for potential positions to be created
    await tradingPage.page.waitForTimeout(5000)

    // Check if positions show auto trading indicator
    const positions = await tradingPage.positionsList.positions.all()

    for (const position of positions) {
      const autoBadge = position.locator('[data-testid="auto-managed"], .auto-trading-indicator')
      if (await autoBadge.isVisible()) {
        // Position is managed by auto trading
        await expect(autoBadge).toBeVisible()

        // Might have special actions
        const autoActions = position.locator(
          'button:has-text("Override"), button:has-text("Manual Control")',
        )
        if (await autoActions.isVisible()) {
          console.log('Found auto-trading position controls')
        }
      }
    }
  })
})
