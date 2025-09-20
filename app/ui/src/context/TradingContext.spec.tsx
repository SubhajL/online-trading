import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { TradingProvider, useTradingContext } from './TradingContext'
import type { Order, Position, Balance, OrderId } from '@/types'

describe('TradingContext', () => {
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <TradingProvider>{children}</TradingProvider>
  )

  it('provides initial state', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    expect(result.current.state.orders).toEqual([])
    expect(result.current.state.positions).toEqual([])
    expect(result.current.state.balances).toEqual([])
    expect(result.current.state.isConnected).toBe(false)
    expect(result.current.state.isLoading).toBe(false)
    expect(result.current.state.error).toBeNull()
  })

  it('updates orders', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const newOrders: Order[] = [
      {
        orderId: 'ORD001' as OrderId,
        symbol: 'BTCUSDT' as any,
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.1,
        price: 40000,
        status: 'NEW',
        venue: 'SPOT',
        createdAt: '2024-01-15T10:00:00Z',
        updatedAt: '2024-01-15T10:00:00Z',
        executedQuantity: 0,
      },
    ]

    act(() => {
      result.current.actions.setOrders(newOrders)
    })

    expect(result.current.state.orders).toEqual(newOrders)
  })

  it('updates single order', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const initialOrder: Order = {
      orderId: 'ORD001' as OrderId,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: 40000,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: '2024-01-15T10:00:00Z',
      updatedAt: '2024-01-15T10:00:00Z',
      executedQuantity: 0,
    }

    act(() => {
      result.current.actions.setOrders([initialOrder])
    })

    const orderUpdate: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
      executedQuantity: 0.1,
      updatedAt: '2024-01-15T10:05:00Z',
    }

    act(() => {
      result.current.actions.updateOrder(orderUpdate)
    })

    expect(result.current.state.orders[0]).toMatchObject({
      ...initialOrder,
      ...orderUpdate,
    })
  })

  it('adds new order', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const newOrder: Order = {
      orderId: 'ORD001' as OrderId,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0,
    }

    act(() => {
      result.current.actions.addOrder(newOrder)
    })

    expect(result.current.state.orders).toContainEqual(newOrder)
  })

  it('updates positions', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const newPositions: Position[] = [
      {
        symbol: 'BTCUSDT' as any,
        side: 'BUY',
        quantity: 0.1,
        entryPrice: 40000,
        markPrice: 42000,
        pnl: 200,
        pnlPercent: 5,
        venue: 'SPOT',
      },
    ]

    act(() => {
      result.current.actions.setPositions(newPositions)
    })

    expect(result.current.state.positions).toEqual(newPositions)
  })

  it('updates balances', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const newBalances: Balance[] = [
      {
        asset: 'USDT',
        free: 10000,
        locked: 500,
        venue: 'SPOT',
      },
    ]

    act(() => {
      result.current.actions.setBalances(newBalances)
    })

    expect(result.current.state.balances).toEqual(newBalances)
  })

  it('updates connection state', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    act(() => {
      result.current.actions.setConnectionState(true)
    })

    expect(result.current.state.isConnected).toBe(true)

    act(() => {
      result.current.actions.setConnectionState(false)
    })

    expect(result.current.state.isConnected).toBe(false)
  })

  it('updates loading state', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    act(() => {
      result.current.actions.setLoading(true)
    })

    expect(result.current.state.isLoading).toBe(true)

    act(() => {
      result.current.actions.setLoading(false)
    })

    expect(result.current.state.isLoading).toBe(false)
  })

  it('sets error', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const error = new Error('Test error')

    act(() => {
      result.current.actions.setError(error)
    })

    expect(result.current.state.error).toEqual(error)

    act(() => {
      result.current.actions.clearError()
    })

    expect(result.current.state.error).toBeNull()
  })

  it('resets state', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    // Set some state
    act(() => {
      result.current.actions.setOrders([
        {
          orderId: 'ORD001' as OrderId,
          symbol: 'BTCUSDT' as any,
          side: 'BUY',
          type: 'MARKET',
          quantity: 0.1,
          status: 'NEW',
          venue: 'SPOT',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          executedQuantity: 0,
        },
      ])
      result.current.actions.setConnectionState(true)
      result.current.actions.setLoading(true)
      result.current.actions.setError(new Error('Test'))
    })

    // Reset
    act(() => {
      result.current.actions.reset()
    })

    expect(result.current.state.orders).toEqual([])
    expect(result.current.state.positions).toEqual([])
    expect(result.current.state.balances).toEqual([])
    expect(result.current.state.isConnected).toBe(false)
    expect(result.current.state.isLoading).toBe(false)
    expect(result.current.state.error).toBeNull()
  })

  it('throws error when used outside provider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      renderHook(() => useTradingContext())
    }).toThrow('useTradingContext must be used within a TradingProvider')

    consoleSpy.mockRestore()
  })

  it('handles concurrent updates correctly', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const order1: Order = {
      orderId: 'ORD001' as OrderId,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0,
    }

    const order2: Order = {
      ...order1,
      orderId: 'ORD002' as OrderId,
      symbol: 'ETHUSDT' as any,
    }

    act(() => {
      result.current.actions.addOrder(order1)
      result.current.actions.addOrder(order2)
    })

    expect(result.current.state.orders).toHaveLength(2)
    expect(result.current.state.orders).toContainEqual(order1)
    expect(result.current.state.orders).toContainEqual(order2)
  })

  it('preserves other state when updating single property', () => {
    const { result } = renderHook(() => useTradingContext(), { wrapper })

    const initialOrders = [
      {
        orderId: 'ORD001' as OrderId,
        symbol: 'BTCUSDT' as any,
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.1,
        status: 'NEW' as const,
        venue: 'SPOT' as const,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0,
      },
    ]

    const initialPositions: Position[] = [
      {
        symbol: 'ETHUSDT' as any,
        side: 'SELL',
        quantity: 1,
        entryPrice: 2500,
        markPrice: 2400,
        pnl: 100,
        pnlPercent: 4,
        venue: 'USD_M',
      },
    ]

    // Set initial state
    act(() => {
      result.current.actions.setOrders(initialOrders)
      result.current.actions.setPositions(initialPositions)
      result.current.actions.setConnectionState(true)
    })

    // Update only loading state
    act(() => {
      result.current.actions.setLoading(true)
    })

    // Check other state is preserved
    expect(result.current.state.orders).toEqual(initialOrders)
    expect(result.current.state.positions).toEqual(initialPositions)
    expect(result.current.state.isConnected).toBe(true)
    expect(result.current.state.isLoading).toBe(true)
  })
})
