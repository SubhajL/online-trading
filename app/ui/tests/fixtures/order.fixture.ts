import { test as base, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export type OrderFixtures = {
  orderPage: OrderPage
  mockOrderAPI: MockOrderAPI
}

export class OrderPage {
  constructor(public readonly page: Page) {}

  // Order form elements
  get symbolInput() { return this.page.locator('[data-testid="symbol-input"]') }
  get sideSelect() { return this.page.locator('[data-testid="side-select"]') }
  get typeSelect() { return this.page.locator('[data-testid="type-select"]') }
  get quantityInput() { return this.page.locator('[data-testid="quantity-input"]') }
  get priceInput() { return this.page.locator('[data-testid="price-input"]') }
  get leverageSelect() { return this.page.locator('[data-testid="leverage-select"]') }
  get submitButton() { return this.page.locator('[data-testid="place-order-btn"]') }

  // Order list elements
  get orderList() { return this.page.locator('[data-testid="order-list"]') }
  get orderItems() { return this.page.locator('[data-testid="order-item"]') }
  get statusFilter() { return this.page.locator('[data-testid="status-filter"]') }

  // Position elements
  get positionList() { return this.page.locator('[data-testid="position-list"]') }
  get positionItems() { return this.page.locator('[data-testid="position-item"]') }

  async goto() {
    await this.page.goto('/trading')
  }

  async placeMarketOrder(symbol: string, side: 'BUY' | 'SELL', quantity: string) {
    await this.symbolInput.fill(symbol)
    await this.sideSelect.selectOption(side)
    await this.typeSelect.selectOption('MARKET')
    await this.quantityInput.fill(quantity)
    await this.submitButton.click()
  }

  async placeLimitOrder(symbol: string, side: 'BUY' | 'SELL', quantity: string, price: string) {
    await this.symbolInput.fill(symbol)
    await this.sideSelect.selectOption(side)
    await this.typeSelect.selectOption('LIMIT')
    await this.quantityInput.fill(quantity)
    await this.priceInput.fill(price)
    await this.submitButton.click()
  }

  async placeBracketOrder(symbol: string, side: 'BUY' | 'SELL', quantity: string, entry: string, stopLoss: string, takeProfit: string) {
    await this.symbolInput.fill(symbol)
    await this.sideSelect.selectOption(side)
    await this.typeSelect.selectOption('BRACKET')
    await this.quantityInput.fill(quantity)
    await this.priceInput.fill(entry)
    
    // Fill stop loss and take profit (assuming these fields exist)
    await this.page.fill('[data-testid="stop-loss-input"]', stopLoss)
    await this.page.fill('[data-testid="take-profit-input"]', takeProfit)
    
    await this.submitButton.click()
  }

  async cancelOrder(orderId: string) {
    const orderRow = this.orderItems.filter({ hasText: orderId })
    await orderRow.locator('[data-testid="cancel-btn"]').click()
    
    // Confirm cancellation if modal appears
    const confirmBtn = this.page.locator('[data-testid="confirm-cancel-btn"]')
    if (await confirmBtn.isVisible({ timeout: 2000 })) {
      await confirmBtn.click()
    }
  }

  async filterOrdersByStatus(status: string) {
    await this.statusFilter.selectOption(status)
  }

  async waitForOrderExecution(timeout = 10000) {
    await this.page.waitForSelector('[data-testid="order-item"]', {
      state: 'visible',
      timeout,
    })
  }

  async getOrderCount() {
    return await this.orderItems.count()
  }

  async getPositionCount() {
    return await this.positionItems.count()
  }

  async expectOrderInList(symbol: string, side: string, status: string) {
    const orderRow = this.orderItems.filter({ hasText: symbol })
    await expect(orderRow).toContainText(side)
    await expect(orderRow).toContainText(status)
  }

  async expectPositionExists(symbol: string, side: string) {
    const positionRow = this.positionItems.filter({ hasText: symbol })
    await expect(positionRow).toContainText(side)
    await expect(positionRow).toBeVisible()
  }
}

export class MockOrderAPI {
  constructor(public readonly page: Page) {}

  async mockSuccessfulOrder(orderData: any) {
    await this.page.route('**/api/trading/orders', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          order: {
            id: 'mock-order-' + Date.now(),
            ...orderData,
            status: 'NEW',
            timestamp: new Date().toISOString(),
          },
        }),
      })
    })
  }

  async mockOrderRejection(reason: string) {
    await this.page.route('**/api/trading/orders', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: reason,
        }),
      })
    })
  }

  async mockInsufficientBalance() {
    await this.mockOrderRejection('Insufficient balance')
  }

  async mockExchangeDowntime() {
    await this.page.route('**/api/trading/orders', async (route) => {
      await route.abort('connectionrefused')
    })
  }
}

export const orderTest = base.extend<OrderFixtures>({
  orderPage: async ({ page }, use) => {
    const orderPage = new OrderPage(page)
    await use(orderPage)
  },

  mockOrderAPI: async ({ page }, use) => {
    const mockAPI = new MockOrderAPI(page)
    await use(mockAPI)
  },
})

export { expect } from '@playwright/test'
