import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useBalances } from './useBalances'
import { _testOnlyExports } from './useApiCache'
import type { Balance } from '@/types'

describe('useBalances', () => {
  const sampleBalances: Balance[] = [
    { asset: 'USDT', free: 1000, locked: 0, total: 1000, venue: 'SPOT', usdValue: 1000 },
    { asset: 'BTC', free: 0.1, locked: 0, total: 0.1, venue: 'SPOT', usdValue: 4000 },
    { asset: 'USDT', free: 2000, locked: 0, total: 2000, venue: 'USD_M', usdValue: 2000 },
  ]

  beforeEach(() => {
    _testOnlyExports.cache.clear()
    _testOnlyExports.inFlightRequests.clear()
    vi.clearAllMocks()
  })

  it('fetches balances from the injected ApiClient', async () => {
    const get = vi.fn().mockResolvedValue(sampleBalances)
    const mockClient = { get } as any

    const { result } = renderHook(() => useBalances(undefined, mockClient))

    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.balances).toEqual([])

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(get).toHaveBeenCalledWith('/balances', { params: undefined })
    expect(result.current.error).toBeNull()
    expect(result.current.balances).toEqual(sampleBalances)
  })

  it('passes venue filter as query param', async () => {
    const spotBalances = sampleBalances.filter(b => b.venue === 'SPOT')
    const get = vi.fn().mockResolvedValue(spotBalances)
    const mockClient = { get } as any

    const { result } = renderHook(() => useBalances('SPOT', mockClient))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(get).toHaveBeenCalledWith('/balances', { params: { venue: 'SPOT' } })
    expect(result.current.balances).toEqual(spotBalances)
  })

  it('uses cache for subsequent hooks with same key', async () => {
    const get = vi.fn().mockResolvedValue(sampleBalances)
    const mockClient = { get } as any

    const { result: result1 } = renderHook(() => useBalances(undefined, mockClient))
    await waitFor(() => {
      expect(result1.current.loading).toBe(false)
    })

    const { result: result2 } = renderHook(() => useBalances(undefined, mockClient))
    expect(result2.current.loading).toBe(false)
    expect(result2.current.balances).toEqual(sampleBalances)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('refresh triggers refetch', async () => {
    const get = vi.fn().mockResolvedValueOnce(sampleBalances).mockResolvedValueOnce(sampleBalances)
    const mockClient = { get } as any

    const { result } = renderHook(() => useBalances(undefined, mockClient))
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    await act(async () => {
      await result.current.refresh()
    })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('deduplicates concurrent requests', async () => {
    const get = vi.fn().mockResolvedValue(sampleBalances)
    const mockClient = { get } as any

    const { result: result1 } = renderHook(() => useBalances(undefined, mockClient))
    const { result: result2 } = renderHook(() => useBalances(undefined, mockClient))

    expect(result1.current.loading).toBe(true)
    expect(result2.current.loading).toBe(true)

    await waitFor(() => {
      expect(result1.current.loading).toBe(false)
      expect(result2.current.loading).toBe(false)
    })

    expect(get).toHaveBeenCalledTimes(1)
    expect(result1.current.balances).toEqual(sampleBalances)
    expect(result2.current.balances).toEqual(sampleBalances)
  })

  it('surfaces ApiClient errors as strings', async () => {
    const get = vi.fn().mockRejectedValue(new Error('Boom'))
    const mockClient = { get } as any

    const { result } = renderHook(() => useBalances(undefined, mockClient))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.balances).toEqual([])
    expect(result.current.error).toContain('Boom')
  })

  describe('optimistic updates', () => {
    const spotBalances: Balance[] = [
      { asset: 'USDT', free: 10000, locked: 0, total: 10000, venue: 'SPOT' },
      { asset: 'BTC', free: 0.5, locked: 0, total: 0.5, venue: 'SPOT' },
    ]

    it('applyOptimistic updates balances immediately for BUY order', async () => {
      const get = vi.fn().mockResolvedValue(spotBalances)
      const mockClient = { get } as any

      const { result } = renderHook(() => useBalances('SPOT', mockClient))
      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      act(() => {
        result.current.applyOptimistic(
          { symbol: 'BTCUSDT', side: 'BUY', type: 'MARKET', quantity: 0.1 },
          50000,
        )
      })

      const usdt = result.current.balances.find(b => b.asset === 'USDT')
      const btc = result.current.balances.find(b => b.asset === 'BTC')
      expect(usdt?.free).toBe(5000)
      expect(btc?.free).toBe(0.6)
    })

    it('rollback restores snapshot after optimistic apply', async () => {
      const get = vi.fn().mockResolvedValue(spotBalances)
      const mockClient = { get } as any

      const { result } = renderHook(() => useBalances('SPOT', mockClient))
      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      let token: any
      act(() => {
        token = result.current.applyOptimistic(
          { symbol: 'BTCUSDT', side: 'BUY', type: 'MARKET', quantity: 0.1 },
          50000,
        )
      })

      act(() => {
        result.current.rollback(token)
      })

      expect(result.current.balances).toEqual(spotBalances)
    })

    it('refresh clears optimistic state', async () => {
      const get = vi.fn().mockResolvedValue(spotBalances)
      const mockClient = { get } as any

      const { result } = renderHook(() => useBalances('SPOT', mockClient))
      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      act(() => {
        result.current.applyOptimistic(
          { symbol: 'BTCUSDT', side: 'BUY', type: 'MARKET', quantity: 0.1 },
          50000,
        )
      })

      await act(async () => {
        await result.current.refresh()
      })

      expect(result.current.balances).toEqual(spotBalances)
    })
  })
})
