import type { Page } from '@playwright/test'

export interface TestOrder {
  id?: string
  symbol: string
  side: 'BUY' | 'SELL'
  type: 'MARKET' | 'LIMIT' | 'BRACKET'
  quantity: string
  price?: string
  status: 'NEW' | 'PENDING' | 'FILLED' | 'CANCELLED' | 'REJECTED'
  timestamp?: string
}

export interface TestPosition {
  symbol: string
  side: 'LONG' | 'SHORT'
  quantity: string
  entryPrice: string
  unrealizedPnl: string
  timestamp?: string
}

export interface TestBalance {
  asset: string
  free: string
  locked: string
  total: string
}

export interface TestCandle {
  symbol: string
  timeframe: string
  openTime: number
  closeTime: number
  open: string
  high: string
  low: string
  close: string
  volume: string
}

export class TestDataSeeder {
  constructor(private page: Page) {}

  async seedOrders(orders: TestOrder[]) {
    const ordersWithDefaults = orders.map(order => ({
      id: order.id || `test-order-${Date.now()}-${Math.random()}`,
      timestamp: order.timestamp || new Date().toISOString(),
      ...order,
    }))

    await this.page.request.post('http://localhost:8002/api/test/seed/orders', {
      data: { orders: ordersWithDefaults },
    })

    return ordersWithDefaults
  }

  async seedPositions(positions: TestPosition[]) {
    const positionsWithDefaults = positions.map(position => ({
      timestamp: position.timestamp || new Date().toISOString(),
      ...position,
    }))

    await this.page.request.post('http://localhost:8002/api/test/seed/positions', {
      data: { positions: positionsWithDefaults },
    })

    return positionsWithDefaults
  }

  async seedBalances(balances: TestBalance[]) {
    await this.page.request.post('http://localhost:8002/api/test/seed/balances', {
      data: { balances },
    })

    return balances
  }

  async seedCandles(candles: TestCandle[]) {
    await this.page.request.post('http://localhost:8002/api/test/seed/candles', {
      data: { candles },
    })

    return candles
  }

  async clearAllTestData() {
    await this.page.request.delete('http://localhost:8002/api/test/cleanup')
  }

  // Predefined test data sets
  async seedBasicTradingScenario() {
    const orders = await this.seedOrders([
      {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: '0.001',
        status: 'FILLED',
        price: '42000.00',
      },
      {
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: '0.1',
        status: 'PENDING',
        price: '3000.00',
      },
    ])

    const positions = await this.seedPositions([
      {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: '0.001',
        entryPrice: '42000.00',
        unrealizedPnl: '50.00',
      },
    ])

    const balances = await this.seedBalances([
      { asset: 'USDT', free: '1000.00', locked: '300.00', total: '1300.00' },
      { asset: 'BTC', free: '0.001', locked: '0.000', total: '0.001' },
    ])

    return { orders, positions, balances }
  }

  async seedMultiplePositionsScenario() {
    const positions = await this.seedPositions([
      {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: '0.002',
        entryPrice: '41000.00',
        unrealizedPnl: '100.00',
      },
      {
        symbol: 'ETHUSDT',
        side: 'SHORT',
        quantity: '0.5',
        entryPrice: '3200.00',
        unrealizedPnl: '-25.00',
      },
      {
        symbol: 'ADAUSDT',
        side: 'LONG',
        quantity: '1000',
        entryPrice: '0.45',
        unrealizedPnl: '15.00',
      },
    ])

    return { positions }
  }

  async seedOrderHistoryScenario() {
    const orders = await this.seedOrders([
      {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: '0.001',
        status: 'FILLED',
        price: '40000.00',
        timestamp: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
      },
      {
        symbol: 'BTCUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: '0.001',
        status: 'FILLED',
        price: '42000.00',
        timestamp: new Date(Date.now() - 43200000).toISOString(), // 12 hours ago
      },
      {
        symbol: 'ETHUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: '0.1',
        status: 'FILLED',
        price: '3000.00',
        timestamp: new Date(Date.now() - 21600000).toISOString(), // 6 hours ago
      },
      {
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: '0.05',
        status: 'CANCELLED',
        price: '3500.00',
        timestamp: new Date(Date.now() - 10800000).toISOString(), // 3 hours ago
      },
    ])

    return { orders }
  }

  async seedPerformanceTestData() {
    // Create 100 orders for performance testing
    const orders: TestOrder[] = []
    for (let i = 0; i < 100; i++) {
      orders.push({
        symbol: i % 2 === 0 ? 'BTCUSDT' : 'ETHUSDT',
        side: i % 2 === 0 ? 'BUY' : 'SELL',
        type: 'MARKET',
        quantity: (Math.random() * 0.01).toFixed(6),
        status: 'FILLED',
        price: (40000 + Math.random() * 5000).toFixed(2),
        timestamp: new Date(Date.now() - i * 60000).toISOString(), // 1 minute intervals
      })
    }

    return await this.seedOrders(orders)
  }
}
