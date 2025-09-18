import { test as base } from '@playwright/test'
import type { Page, Locator } from '@playwright/test'

// Page Objects
export class TradingPage {
  readonly page: Page
  readonly orderForm: {
    symbolInput: Locator
    sideSelect: Locator
    typeSelect: Locator
    quantityInput: Locator
    priceInput: Locator
    submitButton: Locator
  }
  readonly positionsList: {
    container: Locator
    positions: Locator
  }
  readonly orderHistory: {
    container: Locator
    orders: Locator
    statusFilter: Locator
  }
  readonly autoTrading: {
    toggle: Locator
    status: Locator
  }
  readonly accountBalance: {
    totalBalance: Locator
    availableBalance: Locator
  }
  readonly candlestickChart: {
    container: Locator
    timeframeButtons: Locator
  }
  readonly volumeChart: {
    container: Locator
  }

  constructor(page: Page) {
    this.page = page

    // Order Form
    this.orderForm = {
      symbolInput: page.locator('input[placeholder="Enter symbol"]'),
      sideSelect: page.locator('[data-testid="order-side-select"]'),
      typeSelect: page.locator('[data-testid="order-type-select"]'),
      quantityInput: page.locator('input[placeholder="Enter quantity"]'),
      priceInput: page.locator('input[placeholder="Enter price"]'),
      submitButton: page.locator('button:has-text("Place Order")'),
    }

    // Positions List
    this.positionsList = {
      container: page.locator('[data-testid="positions-list"]'),
      positions: page.locator('[data-testid="position-item"]'),
    }

    // Order History
    this.orderHistory = {
      container: page.locator('[data-testid="order-history"]'),
      orders: page.locator('[data-testid="order-item"]'),
      statusFilter: page.locator('[data-testid="status-filter"]'),
    }

    // Auto Trading
    this.autoTrading = {
      toggle: page.locator('[data-testid="auto-trading-toggle"]'),
      status: page.locator('[data-testid="auto-trading-status"]'),
    }

    // Account Balance
    this.accountBalance = {
      totalBalance: page.locator('[data-testid="total-balance"]'),
      availableBalance: page.locator('[data-testid="available-balance"]'),
    }

    // Candlestick Chart
    this.candlestickChart = {
      container: page.locator('[data-testid="candlestick-chart"]'),
      timeframeButtons: page.locator('[data-testid^="timeframe-"]'),
    }

    // Volume Chart
    this.volumeChart = {
      container: page.locator('[data-testid="volume-chart"]'),
    }
  }

  async goto() {
    await this.page.goto('/')
  }

  async placeOrder(order: {
    symbol: string
    side: 'BUY' | 'SELL'
    type: 'MARKET' | 'LIMIT'
    quantity: number
    price?: number
  }) {
    await this.orderForm.symbolInput.fill(order.symbol)
    await this.orderForm.sideSelect.selectOption(order.side)
    await this.orderForm.typeSelect.selectOption(order.type)
    await this.orderForm.quantityInput.fill(order.quantity.toString())

    if (order.type === 'LIMIT' && order.price) {
      await this.orderForm.priceInput.fill(order.price.toString())
    }

    await this.orderForm.submitButton.click()
  }

  async waitForOrderExecution() {
    // Wait for order to appear in history
    await this.page.waitForSelector('[data-testid="order-item"]', {
      state: 'visible',
      timeout: 10000,
    })
  }

  async selectTimeframe(timeframe: string) {
    await this.page.locator(`[data-testid="timeframe-${timeframe}"]`).click()
  }

  async toggleAutoTrading() {
    await this.autoTrading.toggle.click()
  }

  async filterOrdersByStatus(status: string) {
    await this.orderHistory.statusFilter.selectOption(status)
  }
}

// Fixtures
export const test = base.extend<{
  tradingPage: TradingPage
}>({
  tradingPage: async ({ page }, use) => {
    const tradingPage = new TradingPage(page)
    await use(tradingPage)
  },
})

export { expect } from '@playwright/test'
