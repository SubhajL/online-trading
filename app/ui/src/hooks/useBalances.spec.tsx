import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useBalances } from './useBalances'
import { ApiClient } from '@/services/api.client'
import { _testOnlyExports } from './useApiCache'

describe('useBalances', () => {
  let apiClient: ApiClient

  beforeAll(() => {
    // Create real API client pointing to BFF
    apiClient = new ApiClient({
      baseUrl: 'http://localhost:8002/api',
      timeout: 30000,
    })
  })

  afterEach(() => {
    // Clear any cache after each test
    _testOnlyExports.cache.clear()
    _testOnlyExports.inFlightRequests.clear()
  })

  it('fetches real balances from the API', async () => {
    const { result } = renderHook(() => useBalances(undefined, apiClient))

    // Initial state
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.balances).toEqual([])

    // Wait for data to load
    await waitFor(
      () => {
        expect(result.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    // Verify we got real balance data
    expect(result.current.error).toBeNull()
    expect(result.current.balances.length).toBeGreaterThan(0)

    // Verify balance structure
    const firstBalance = result.current.balances[0]
    expect(firstBalance).toHaveProperty('asset')
    expect(firstBalance).toHaveProperty('free')
    expect(firstBalance).toHaveProperty('locked')
    expect(firstBalance).toHaveProperty('total')
    expect(firstBalance).toHaveProperty('venue')
    expect(firstBalance).toHaveProperty('usdValue')

    // Verify numeric values
    expect(typeof firstBalance.free).toBe('number')
    expect(typeof firstBalance.locked).toBe('number')
    expect(typeof firstBalance.total).toBe('number')
    expect(typeof firstBalance.usdValue).toBe('number')

    // Verify venue values
    expect(['SPOT', 'USD_M']).toContain(firstBalance.venue)
  })

  it('filters balances by venue', async () => {
    const { result } = renderHook(() => useBalances('SPOT', apiClient))

    await waitFor(
      () => {
        expect(result.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    expect(result.current.error).toBeNull()

    // All balances should be SPOT venue
    result.current.balances.forEach(balance => {
      expect(balance.venue).toBe('SPOT')
    })
  })

  it('uses cache for subsequent requests', async () => {
    // First request
    const { result: result1 } = renderHook(() => useBalances(undefined, apiClient))

    await waitFor(
      () => {
        expect(result1.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    const firstCallBalances = result1.current.balances

    // Second request should use cache
    const { result: result2 } = renderHook(() => useBalances(undefined, apiClient))

    // Should immediately have data from cache
    expect(result2.current.loading).toBe(false)
    expect(result2.current.balances).toEqual(firstCallBalances)
  })

  it('allows manual refetch', async () => {
    const { result } = renderHook(() => useBalances(undefined, apiClient))

    // Wait for initial load
    await waitFor(
      () => {
        expect(result.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    // Refetch
    act(() => {
      result.current.refresh()
    })

    // Should be loading again
    expect(result.current.loading).toBe(true)

    // Wait for refetch to complete
    await waitFor(
      () => {
        expect(result.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    // Should have balances (might be same as initial if no changes)
    expect(result.current.balances.length).toBeGreaterThan(0)
  })

  it('deduplicates concurrent requests', async () => {
    // Render two hooks at the same time
    const { result: result1 } = renderHook(() => useBalances(undefined, apiClient))
    const { result: result2 } = renderHook(() => useBalances(undefined, apiClient))

    // Both should be loading
    expect(result1.current.loading).toBe(true)
    expect(result2.current.loading).toBe(true)

    // Wait for both to complete
    await waitFor(
      () => {
        expect(result1.current.loading).toBe(false)
        expect(result2.current.loading).toBe(false)
      },
      { timeout: 10000 },
    )

    // Both should have the same data
    expect(result1.current.balances).toEqual(result2.current.balances)
    expect(result1.current.error).toBeNull()
    expect(result2.current.error).toBeNull()
  })

  it('handles API errors gracefully', async () => {
    // Use a client with wrong URL to trigger error
    const errorClient = new ApiClient({
      baseUrl: 'http://localhost:9999/api', // Wrong port
      timeout: 2000,
    })

    const { result } = renderHook(() => useBalances(undefined, errorClient))

    // Initial state should be loading
    expect(result.current.loading).toBe(true)

    // Wait for error
    await waitFor(
      () => {
        expect(result.current.loading).toBe(false)
      },
      { timeout: 5000 },
    )

    // Should have error
    expect(result.current.error).not.toBeNull()
    expect(typeof result.current.error).toBe('string')
    expect(result.current.balances).toEqual([])
  })
})
