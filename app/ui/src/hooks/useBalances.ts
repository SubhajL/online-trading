import { useMemo, useRef } from 'react'
import { apiClient } from '@/services/api'
import { ApiClient } from '@/services/api.client'
import type { Balance, Venue } from '@/types'
import { useApiCache } from './useApiCache'

type UseBalancesReturn = {
  balances: Balance[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useBalances(venue?: Venue, client?: ApiClient): UseBalancesReturn {
  const apiClientRef = useRef(client || apiClient)

  const cacheKey = useMemo(
    () => venue ? `balances-${venue}` : 'balances-all',
    [venue]
  )

  const fetcher = useMemo(
    () => async () => {
      const params = venue ? { venue } : undefined
      const data = await apiClientRef.current.get<Balance[]>('/balances', { params })
      return data
    },
    [venue]
  )

  const { data, loading, error, refetch } = useApiCache<Balance[]>(
    cacheKey,
    fetcher,
    { ttl: 30000 } // 30 seconds cache
  )

  return {
    balances: data || [],
    loading,
    error: error ? error.message || String(error) : null,
    refresh: refetch,
  }
}
