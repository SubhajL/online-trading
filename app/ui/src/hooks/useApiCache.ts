import { useState, useEffect, useCallback, useRef } from 'react'

type CacheEntry<T> = {
  data: T
  timestamp: number
  ttl: number
}

type CacheOptions = {
  ttl?: number // Time to live in milliseconds
}

// Global cache store
const cache = new Map<string, CacheEntry<unknown>>()
// Track in-flight requests for deduplication
const inFlightRequests = new Map<string, Promise<unknown>>()

// Export for testing only
export const _testOnlyExports = {
  cache,
  inFlightRequests,
}

const DEFAULT_TTL = 5 * 60 * 1000 // 5 minutes

function isCacheValid<T>(entry: CacheEntry<T> | undefined): entry is CacheEntry<T> {
  if (!entry) return false
  if (entry.ttl === 0) return false
  return Date.now() - entry.timestamp < entry.ttl
}

export function useApiCache<T>(
  cacheKey: string,
  fetcher: () => Promise<T>,
  options: CacheOptions = {},
) {
  const { ttl = DEFAULT_TTL } = options

  // Check initial cache state
  const getCachedData = () => {
    const cached = cache.get(cacheKey) as CacheEntry<T> | undefined
    return isCacheValid(cached) ? cached.data : null
  }

  const [data, setData] = useState<T | null>(getCachedData)
  const [loading, setLoading] = useState(() => {
    const cached = cache.get(cacheKey) as CacheEntry<T> | undefined
    return !isCacheValid(cached)
  })
  const [error, setError] = useState<Error | null>(null)
  const mountedRef = useRef(true)

  const fetchData = useCallback(
    async (force = false) => {
      // Check cache first
      if (!force) {
        const cached = cache.get(cacheKey) as CacheEntry<T> | undefined
        if (isCacheValid(cached)) {
          setData(cached.data)
          setLoading(false)
          setError(null)
          return
        }
      }

      // Check if there's already a request in flight
      const inFlight = inFlightRequests.get(cacheKey) as Promise<T> | undefined
      if (inFlight && !force) {
        setLoading(true)
        try {
          const result = await inFlight
          if (mountedRef.current) {
            setData(result)
            setError(null)
          }
        } catch (err) {
          if (mountedRef.current) {
            setError(err instanceof Error ? err : new Error('Unknown error'))
            setData(null)
          }
        } finally {
          if (mountedRef.current) {
            setLoading(false)
          }
        }
        return
      }

      // Make new request
      setLoading(true)
      setError(null)

      const request = fetcher()
      inFlightRequests.set(cacheKey, request)

      try {
        const result = await request

        // Update cache
        cache.set(cacheKey, {
          data: result,
          timestamp: Date.now(),
          ttl,
        })

        if (mountedRef.current) {
          setData(result)
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err : new Error('Unknown error'))
          setData(null)
        }
      } finally {
        inFlightRequests.delete(cacheKey)
        if (mountedRef.current) {
          setLoading(false)
        }
      }
    },
    [cacheKey, fetcher, ttl],
  )

  const clearCache = useCallback(() => {
    cache.delete(cacheKey)
    fetchData(true)
  }, [cacheKey, fetchData])

  const refetch = useCallback(() => {
    fetchData(true)
  }, [fetchData])

  useEffect(() => {
    mountedRef.current = true
    fetchData()

    return () => {
      mountedRef.current = false
    }
  }, [fetchData])

  return {
    data,
    loading,
    error,
    refetch,
    clearCache,
  }
}
