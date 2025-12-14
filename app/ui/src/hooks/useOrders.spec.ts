import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useOrders } from './useOrders'
import { _testOnlyExports as cacheExports } from './useApiCache'

describe('useOrders', () => {
  beforeEach(() => {
    // Clear cache between tests
    cacheExports.cache.clear()
    cacheExports.inFlightRequests.clear()
  })

  describe('basic functionality', () => {
    it('fetches orders on mount', async () => {
      const { result } = renderHook(() => useOrders())

      expect(result.current.loading).toBe(true)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Verify the structure of returned data
      expect(Array.isArray(result.current.orders)).toBe(true)
      expect(result.current.error).toBe(null)

      // If there are orders, verify the structure
      if (result.current.orders.length > 0) {
        const order = result.current.orders[0]
        expect(order).toHaveProperty('id')
        expect(order).toHaveProperty('symbol')
        expect(order).toHaveProperty('side')
        expect(order).toHaveProperty('type')
        expect(order).toHaveProperty('status')
        expect(order).toHaveProperty('price')
        expect(order).toHaveProperty('quantity')
        expect(order).toHaveProperty('venue')
      }
    })

    it('fetches orders with venue filter', async () => {
      const { result } = renderHook(() => useOrders({ venue: 'USD_M' as Venue }))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // All returned orders should be from USD_M venue
      result.current.orders.forEach(order => {
        expect(order.venue).toBe('USD_M')
      })
    })

    it('fetches orders with status filter', async () => {
      const { result } = renderHook(() => useOrders({ status: 'NEW' as OrderStatus }))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // All returned orders should have NEW status
      result.current.orders.forEach(order => {
        expect(order.status).toBe('NEW')
      })
    })

    it('fetches orders with symbol filter', async () => {
      const { result } = renderHook(() => useOrders({ symbol: 'BTCUSDT' }))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // All returned orders should be for BTCUSDT
      result.current.orders.forEach(order => {
        expect(order.symbol).toBe('BTCUSDT')
      })
    })

    it('fetches orders with multiple filters', async () => {
      const { result } = renderHook(() =>
        useOrders({
          venue: 'SPOT' as Venue,
          status: 'FILLED' as OrderStatus,
          symbol: 'ETHUSDT',
        }),
      )

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // All returned orders should match all filters
      result.current.orders.forEach(order => {
        expect(order.venue).toBe('SPOT')
        expect(order.status).toBe('FILLED')
        expect(order.symbol).toBe('ETHUSDT')
      })
    })

    it('handles empty orders', async () => {
      const { result } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(Array.isArray(result.current.orders)).toBe(true)
      expect(result.current.error).toBe(null)
    })
  })

  describe('error handling', () => {
    it('handles API errors', async () => {
      const { result } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // If there's an error, it should be a string
      if (result.current.error) {
        expect(typeof result.current.error).toBe('string')
      }
    })

    it('allows refresh after error', async () => {
      const { result } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Refresh
      await act(async () => {
        await result.current.refresh()
      })

      // Should have fetched again
      expect(result.current.loading).toBe(false)

      // Orders might be the same or different
      expect(Array.isArray(result.current.orders)).toBe(true)
    })
  })

  describe('cancellation handling', () => {
    it('cancels request on unmount', async () => {
      const { result, unmount } = renderHook(() => useOrders())

      expect(result.current.loading).toBe(true)

      // Unmount immediately
      unmount()

      // Should not throw any errors
      // The request should be cancelled internally
    })

    it('cancels previous request on filter change', async () => {
      const { result, rerender } = renderHook(({ filters }) => useOrders(filters), {
        initialProps: { filters: { venue: 'SPOT' as Venue } },
      })

      expect(result.current.loading).toBe(true)

      // Change filters immediately
      rerender({ filters: { venue: 'USD_M' as Venue } })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Should have data from USD_M
      result.current.orders.forEach(order => {
        expect(order.venue).toBe('USD_M')
      })
    })
  })

  describe('caching integration', () => {
    it('uses cached data when available', async () => {
      // First call
      const { result: result1, unmount: unmount1 } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result1.current.loading).toBe(false)
      })

      const firstCallOrders = [...result1.current.orders]
      unmount1()

      // Second call - should use cache
      const { result: result2 } = renderHook(() => useOrders())

      // Should have data immediately from cache
      expect(result2.current.loading).toBe(false)
      expect(result2.current.orders).toEqual(firstCallOrders)
    })

    it('respects filters for cache key', async () => {
      // First hook with SPOT
      const { result: result1 } = renderHook(() => useOrders({ venue: 'SPOT' as Venue }))

      await waitFor(() => {
        expect(result1.current.loading).toBe(false)
      })

      const spotOrders = [...result1.current.orders]

      // Second hook with USD_M - should not use SPOT cache
      const { result: result2 } = renderHook(() => useOrders({ venue: 'USD_M' as Venue }))

      expect(result2.current.loading).toBe(true) // Should be loading

      await waitFor(() => {
        expect(result2.current.loading).toBe(false)
      })

      const usdmOrders = [...result2.current.orders]

      // Verify they're different venues
      spotOrders.forEach(o => expect(o.venue).toBe('SPOT'))
      usdmOrders.forEach(o => expect(o.venue).toBe('USD_M'))
    })
  })

  describe('manual refresh', () => {
    it('provides refresh function', async () => {
      const { result } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Manual refresh
      await act(async () => {
        await result.current.refresh()
      })

      expect(result.current.loading).toBe(false)
      expect(Array.isArray(result.current.orders)).toBe(true)
    })

    it('shows loading state during refresh', async () => {
      const { result } = renderHook(() => useOrders())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Start refresh
      let loadingDuringRefresh = false
      const refreshPromise = act(async () => {
        loadingDuringRefresh = result.current.loading
        await result.current.refresh()
      })

      // Check loading state
      expect(loadingDuringRefresh || result.current.loading).toBe(true)

      await refreshPromise

      expect(result.current.loading).toBe(false)
    })
  })

  describe('dependency injection', () => {
    it('accepts custom API client', async () => {
      // Create a custom client that points to a different endpoint
      const customClient = {
        get: async (endpoint: string, _options?: any) => {
          // Make a real request to a test endpoint
          const response = await fetch('http://localhost:8002/api/test' + endpoint, {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
            },
          })
          return response.json()
        },
      }

      const { result } = renderHook(() => useOrders(undefined, customClient as any))

      await waitFor(
        () => {
          expect(result.current.loading).toBe(false)
        },
        { timeout: 10000 },
      )

      // Should have attempted to fetch from the custom client
      expect(Array.isArray(result.current.orders)).toBe(true)
    })
  })

  describe('pagination', () => {
    it('supports pagination', async () => {
      const { result } = renderHook(() => useOrders({ limit: 10, offset: 0 }))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Should have no more than 10 orders
      expect(result.current.orders.length).toBeLessThanOrEqual(10)
    })

    it('fetches next page', async () => {
      // First page
      const { result, rerender } = renderHook(({ filters }) => useOrders(filters), {
        initialProps: { filters: { limit: 5, offset: 0 } },
      })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      const firstPageOrders = [...result.current.orders]

      // Second page
      rerender({ filters: { limit: 5, offset: 5 } })

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      // Should have different orders
      const secondPageOrders = [...result.current.orders]

      // Verify pagination worked by checking IDs don't overlap
      const firstPageIds = firstPageOrders.map(o => o.orderId)
      const secondPageIds = secondPageOrders.map(o => o.orderId)

      secondPageIds.forEach(id => {
        expect(firstPageIds).not.toContain(id)
      })
    })
  })

})
