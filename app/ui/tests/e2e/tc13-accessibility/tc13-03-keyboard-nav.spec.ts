import { test, expect } from '@playwright/test'
import { AccessibilityHelpers } from '../../utils/accessibility-helpers'

test.describe('TC13.03: Keyboard Navigation', () => {
  let a11yHelpers: AccessibilityHelpers

  test.beforeEach(async ({ page }) => {
    a11yHelpers = new AccessibilityHelpers(page)
    await page.goto('/trading')
  })

  test('should navigate through trading form with Tab key', async ({ page }) => {
    const expectedOrder = [
      'symbol-input',
      'side-select', 
      'type-select',
      'quantity-input',
      'price-input',
      'place-order-btn'
    ]

    await a11yHelpers.checkKeyboardNavigation('symbol-input', expectedOrder)
  })

  test('should navigate through order list with arrow keys', async ({ page }) => {
    // Seed some test orders first
    await page.evaluate(() => {
      // Mock some orders in the list
      const orderList = document.querySelector('[data-testid="order-list"]')
      if (orderList) {
        orderList.innerHTML = `
          <div data-testid="order-item" tabindex="0">Order 1</div>
          <div data-testid="order-item" tabindex="0">Order 2</div>
          <div data-testid="order-item" tabindex="0">Order 3</div>
        `
      }
    })

    // Focus first order
    await page.locator('[data-testid="order-item"]').first().focus()

    // Navigate with arrow keys
    await page.keyboard.press('ArrowDown')
    let focused = await page.evaluate(() => document.activeElement?.textContent)
    expect(focused).toBe('Order 2')

    await page.keyboard.press('ArrowDown')
    focused = await page.evaluate(() => document.activeElement?.textContent)
    expect(focused).toBe('Order 3')

    await page.keyboard.press('ArrowUp')
    focused = await page.evaluate(() => document.activeElement?.textContent)
    expect(focused).toBe('Order 2')
  })

  test('should handle Enter key for button activation', async ({ page }) => {
    await page.locator('[data-testid="place-order-btn"]').focus()
    
    // Mock form submission
    let buttonClicked = false
    await page.evaluate(() => {
      const button = document.querySelector('[data-testid="place-order-btn"]') as HTMLButtonElement
      if (button) {
        button.addEventListener('click', () => {
          (window as any).__buttonClicked = true
        })
      }
    })

    await page.keyboard.press('Enter')

    const clicked = await page.evaluate(() => (window as any).__buttonClicked)
    expect(clicked).toBe(true)
  })

  test('should handle Space key for checkbox/toggle activation', async ({ page }) => {
    // Navigate to settings page with toggles
    await page.goto('/settings')

    const toggle = page.locator('[data-testid="auto-trading-toggle"]')
    if (await toggle.isVisible()) {
      await toggle.focus()
      
      const initialState = await toggle.isChecked()
      await page.keyboard.press('Space')
      
      const newState = await toggle.isChecked()
      expect(newState).toBe(!initialState)
    }
  })

  test('should handle Escape key for modal dismissal', async ({ page }) => {
    // Trigger a modal (e.g., order confirmation)
    await page.fill('[data-testid="symbol-input"]', 'BTCUSDT')
    await page.fill('[data-testid="quantity-input"]', '0.001')
    await page.click('[data-testid="place-order-btn"]')

    // If confirmation modal appears
    const modal = page.locator('[data-testid="order-confirm-modal"]')
    if (await modal.isVisible({ timeout: 2000 })) {
      await page.keyboard.press('Escape')
      await expect(modal).not.toBeVisible()
    }
  })

  test('should skip hidden elements during navigation', async ({ page }) => {
    // Hide an element
    await page.evaluate(() => {
      const element = document.querySelector('[data-testid="price-input"]')
      if (element) {
        (element as HTMLElement).style.display = 'none'
      }
    })

    // Tab through form - should skip hidden price input
    await page.locator('[data-testid="symbol-input"]').focus()
    await page.keyboard.press('Tab') // to side-select
    await page.keyboard.press('Tab') // to type-select
    await page.keyboard.press('Tab') // should skip price-input, go to quantity-input

    const focused = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'))
    expect(focused).toBe('quantity-input')
  })

  test('should handle focus trapping in modals', async ({ page }) => {
    // Open a modal
    await page.click('[data-testid="settings-btn"]')
    
    const modal = page.locator('[data-testid="settings-modal"]')
    if (await modal.isVisible({ timeout: 2000 })) {
      // Focus should be trapped within modal
      const modalElements = await modal.locator('button, input, select, textarea, [tabindex]:not([tabindex="-1"])').all()
      
      if (modalElements.length > 1) {
        // Focus first element
        await modalElements[0].focus()
        
        // Tab to last element
        for (let i = 1; i < modalElements.length; i++) {
          await page.keyboard.press('Tab')
        }
        
        // Tab again should wrap to first element
        await page.keyboard.press('Tab')
        const focused = await page.evaluate(() => document.activeElement)
        const firstElement = await modalElements[0].evaluate(el => el)
        expect(focused).toBe(firstElement)
      }
    }
  })

  test('should provide visual focus indicators', async ({ page }) => {
    const focusableElements = [
      '[data-testid="symbol-input"]',
      '[data-testid="place-order-btn"]',
      '[data-testid="auto-trading-toggle"]'
    ]

    for (const selector of focusableElements) {
      const element = page.locator(selector)
      if (await element.isVisible()) {
        await a11yHelpers.checkFocusVisibility(selector)
      }
    }
  })

  test('should handle custom keyboard shortcuts', async ({ page }) => {
    // Test trading-specific shortcuts
    await page.keyboard.press('Control+b') // Quick buy
    
    // Check if buy side is selected
    const sideSelect = page.locator('[data-testid="side-select"]')
    const selectedValue = await sideSelect.inputValue()
    expect(selectedValue).toBe('BUY')

    await page.keyboard.press('Control+s') // Quick sell
    const newSelectedValue = await sideSelect.inputValue()
    expect(newSelectedValue).toBe('SELL')
  })

  test('should announce dynamic content changes to screen readers', async ({ page }) => {
    // Check for aria-live regions
    const liveRegions = page.locator('[aria-live]')
    await expect(liveRegions).toHaveCount({ min: 1 })

    // Trigger a price update
    await page.evaluate(() => {
      const priceElement = document.querySelector('[data-testid="current-price"]')
      if (priceElement) {
        priceElement.textContent = '$42,500.00'
        // Trigger change event for screen readers
        const event = new Event('change')
        priceElement.dispatchEvent(event)
      }
    })

    // Check that live region is updated
    const liveRegion = page.locator('[aria-live="polite"]').first()
    if (await liveRegion.isVisible()) {
      await expect(liveRegion).toContainText('42,500')
    }
  })

  test('should handle complex navigation patterns', async ({ page }) => {
    // Test navigation in data tables
    const table = page.locator('[data-testid="order-history-table"]')
    if (await table.isVisible()) {
      // Focus first cell
      await table.locator('td').first().focus()
      
      // Navigate with arrow keys
      await page.keyboard.press('ArrowRight') // Next cell
      await page.keyboard.press('ArrowDown')  // Next row
      await page.keyboard.press('Home')       // First cell in row
      await page.keyboard.press('End')        // Last cell in row
      
      // Each navigation should maintain focus within table
      const focused = await page.evaluate(() => {
        const activeElement = document.activeElement
        return activeElement?.closest('[data-testid="order-history-table"]') !== null
      })
      expect(focused).toBe(true)
    }
  })
})
