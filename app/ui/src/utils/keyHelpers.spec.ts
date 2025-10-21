import { describe, expect, test } from 'vitest'
import { getPositionKey, getBalanceKey, getOrderKey } from './keyHelpers'

describe('getPositionKey', () => {
  test('generates unique key combining symbol and index', () => {
    expect(getPositionKey('BTCUSDT', 0)).toBe('position-BTCUSDT-0')
    expect(getPositionKey('ETHUSDT', 1)).toBe('position-ETHUSDT-1')
  })

  test('generates different keys for different symbols', () => {
    const key1 = getPositionKey('BTCUSDT', 0)
    const key2 = getPositionKey('ETHUSDT', 0)
    expect(key1).not.toBe(key2)
  })

  test('generates different keys for same symbol at different indices', () => {
    const key1 = getPositionKey('BTCUSDT', 0)
    const key2 = getPositionKey('BTCUSDT', 1)
    expect(key1).not.toBe(key2)
  })
})

describe('getBalanceKey', () => {
  test('generates unique key combining asset and index', () => {
    expect(getBalanceKey('BTC', 0)).toBe('balance-BTC-0')
    expect(getBalanceKey('ETH', 1)).toBe('balance-ETH-1')
  })

  test('generates different keys for different assets', () => {
    const key1 = getBalanceKey('BTC', 0)
    const key2 = getBalanceKey('ETH', 0)
    expect(key1).not.toBe(key2)
  })

  test('generates different keys for same asset at different indices', () => {
    const key1 = getBalanceKey('USDT', 0)
    const key2 = getBalanceKey('USDT', 1)
    expect(key1).not.toBe(key2)
  })
})

describe('getOrderKey', () => {
  test('generates unique key from orderId', () => {
    expect(getOrderKey('12345' as any)).toBe('order-12345')
    expect(getOrderKey('67890' as any)).toBe('order-67890')
  })

  test('generates different keys for different orderIds', () => {
    const key1 = getOrderKey('order-1' as any)
    const key2 = getOrderKey('order-2' as any)
    expect(key1).not.toBe(key2)
  })
})
