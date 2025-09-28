import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useApiCache, _testOnlyExports } from './useApiCache'

describe('useApiCache', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    // Clear cache between tests
    _testOnlyExports.cache.clear()
    _testOnlyExports.inFlightRequests.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('cache behavior', () => {
    it('returns cached data within TTL', async () => {
      const mockFetcher = vi.fn().mockResolvedValue({ data: 'test' })
      const cacheKey = 'test-key'
      const ttl = 5000 // 5 seconds

      // First call - should fetch
      const { result, rerender } = renderHook(() => useApiCache(cacheKey, mockFetcher, { ttl }))

      expect(result.current.loading).toBe(true)
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'test' })
      expect(result.current.loading).toBe(false)

      // Second call within TTL - should use cache
      rerender()
      expect(mockFetcher).toHaveBeenCalledTimes(1) // Not called again
      expect(result.current.data).toEqual({ data: 'test' })
      expect(result.current.loading).toBe(false)
    })

    it('refetches when cache expires', async () => {
      const mockFetcher = vi
        .fn()
        .mockResolvedValueOnce({ data: 'first' })
        .mockResolvedValueOnce({ data: 'second' })
      const cacheKey = 'test-key'
      const ttl = 5000

      const { result, unmount } = renderHook(() => useApiCache(cacheKey, mockFetcher, { ttl }))

      // Initial fetch
      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'first' })
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      unmount()

      // Advance time past TTL
      act(() => {
        vi.advanceTimersByTime(ttl + 1)
      })

      // Mount again after TTL - should fetch again
      const { result: result2 } = renderHook(() => useApiCache(cacheKey, mockFetcher, { ttl }))

      expect(result2.current.loading).toBe(true)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result2.current.data).toEqual({ data: 'second' })
      expect(result2.current.loading).toBe(false)
      expect(mockFetcher).toHaveBeenCalledTimes(2)
    })

    it('handles cache key collisions', async () => {
      const mockFetcher1 = vi.fn().mockResolvedValue({ data: 'value1' })
      const mockFetcher2 = vi.fn().mockResolvedValue({ data: 'value2' })

      const { result: result1 } = renderHook(() => useApiCache('key1', mockFetcher1))
      const { result: result2 } = renderHook(() => useApiCache('key2', mockFetcher2))

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result1.current.data).toEqual({ data: 'value1' })
      expect(result2.current.data).toEqual({ data: 'value2' })

      expect(mockFetcher1).toHaveBeenCalledTimes(1)
      expect(mockFetcher2).toHaveBeenCalledTimes(1)
    })

    it('clears cache on demand', async () => {
      const mockFetcher = vi
        .fn()
        .mockResolvedValueOnce({ data: 'first' })
        .mockResolvedValueOnce({ data: 'second' })
      const cacheKey = 'test-key'

      const { result } = renderHook(() => useApiCache(cacheKey, mockFetcher))

      // Initial fetch
      await act(async () => {
        await vi.runAllTimersAsync()
      })
      expect(result.current.data).toEqual({ data: 'first' })
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      // Clear cache
      act(() => {
        result.current.clearCache()
      })

      // Should refetch after clearing
      expect(result.current.loading).toBe(true)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'second' })
      expect(result.current.loading).toBe(false)
      expect(mockFetcher).toHaveBeenCalledTimes(2)
    })
  })

  describe('deduplication', () => {
    it('deduplicates concurrent requests', async () => {
      const mockFetcher = vi
        .fn()
        .mockImplementation(
          () => new Promise(resolve => setTimeout(() => resolve({ data: 'test' }), 100)),
        )
      const cacheKey = 'test-key'

      // Mount multiple hooks with same key simultaneously
      const { result: result1 } = renderHook(() => useApiCache(cacheKey, mockFetcher))
      const { result: result2 } = renderHook(() => useApiCache(cacheKey, mockFetcher))
      const { result: result3 } = renderHook(() => useApiCache(cacheKey, mockFetcher))

      // All should be loading
      expect(result1.current.loading).toBe(true)
      expect(result2.current.loading).toBe(true)
      expect(result3.current.loading).toBe(true)

      // But fetcher should only be called once
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      // Wait for promises to resolve
      await act(async () => {
        await vi.runAllTimersAsync()
      })

      // All should receive the same data
      expect(result1.current.data).toEqual({ data: 'test' })
      expect(result2.current.data).toEqual({ data: 'test' })
      expect(result3.current.data).toEqual({ data: 'test' })

      // Still only one call
      expect(mockFetcher).toHaveBeenCalledTimes(1)
    })

    it('handles deduplication with different cache keys', async () => {
      const mockFetcher = vi
        .fn()
        .mockImplementation((key: string) => Promise.resolve({ data: key }))

      const { result: result1 } = renderHook(() => useApiCache('key1', () => mockFetcher('key1')))
      const { result: result2 } = renderHook(() => useApiCache('key2', () => mockFetcher('key2')))

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result1.current.data).toEqual({ data: 'key1' })
      expect(result2.current.data).toEqual({ data: 'key2' })

      // Should be called twice - once for each key
      expect(mockFetcher).toHaveBeenCalledTimes(2)
    })
  })

  describe('error handling', () => {
    it('handles fetch errors', async () => {
      const mockError = new Error('Network error')
      const mockFetcher = vi.fn().mockRejectedValue(mockError)
      const cacheKey = 'test-key'

      const { result } = renderHook(() => useApiCache(cacheKey, mockFetcher))

      expect(result.current.loading).toBe(true)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.error).toBe(mockError)
      expect(result.current.loading).toBe(false)
      expect(result.current.data).toBe(null)
    })

    it('retries after error on manual refetch', async () => {
      const mockFetcher = vi
        .fn()
        .mockRejectedValueOnce(new Error('First error'))
        .mockResolvedValueOnce({ data: 'success' })
      const cacheKey = 'test-key'

      const { result } = renderHook(() => useApiCache(cacheKey, mockFetcher))

      // Initial error
      await act(async () => {
        await vi.runAllTimersAsync()
      })
      expect(result.current.error?.message).toBe('First error')

      // Manual refetch
      act(() => {
        result.current.refetch()
      })

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'success' })
      expect(result.current.error).toBe(null)

      expect(mockFetcher).toHaveBeenCalledTimes(2)
    })
  })

  describe('options', () => {
    it('respects custom TTL', async () => {
      const mockFetcher = vi
        .fn()
        .mockResolvedValueOnce({ data: 'first' })
        .mockResolvedValueOnce({ data: 'second' })
      const cacheKey = 'test-key-ttl'
      const customTtl = 10000 // 10 seconds

      // First mount
      const { result, unmount } = renderHook(() =>
        useApiCache(cacheKey, mockFetcher, { ttl: customTtl }),
      )

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'first' })
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      unmount()

      // Advance time less than TTL
      act(() => {
        vi.advanceTimersByTime(customTtl - 1)
      })

      // Mount again - should use cache
      const { result: result2 } = renderHook(() =>
        useApiCache(cacheKey, mockFetcher, { ttl: customTtl }),
      )

      expect(result2.current.data).toEqual({ data: 'first' })
      expect(result2.current.loading).toBe(false)
      expect(mockFetcher).toHaveBeenCalledTimes(1) // Still cached

      // Advance past TTL
      act(() => {
        vi.advanceTimersByTime(2)
      })

      // Mount once more - should refetch
      const { result: result3 } = renderHook(() =>
        useApiCache(cacheKey, mockFetcher, { ttl: customTtl }),
      )

      expect(result3.current.loading).toBe(true)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result3.current.data).toEqual({ data: 'second' })
      expect(mockFetcher).toHaveBeenCalledTimes(2) // Refetched
    })

    it('disables cache when TTL is 0', async () => {
      const mockFetcher = vi
        .fn()
        .mockResolvedValueOnce({ data: 'first' })
        .mockResolvedValueOnce({ data: 'second' })
      const cacheKey = 'test-key-no-cache'

      // First mount
      const { result, unmount } = renderHook(() => useApiCache(cacheKey, mockFetcher, { ttl: 0 }))

      expect(result.current.loading).toBe(true)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result.current.data).toEqual({ data: 'first' })
      expect(mockFetcher).toHaveBeenCalledTimes(1)

      unmount()

      // Second mount should refetch immediately
      const { result: result2 } = renderHook(() => useApiCache(cacheKey, mockFetcher, { ttl: 0 }))

      expect(result2.current.loading).toBe(true)
      expect(mockFetcher).toHaveBeenCalledTimes(2)

      await act(async () => {
        await vi.runAllTimersAsync()
      })

      expect(result2.current.data).toEqual({ data: 'second' })
    })
  })
})
