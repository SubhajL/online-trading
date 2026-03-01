import { useMemo, useRef, useState, useCallback } from 'react'
import { apiClient } from '@/services/api'
import type { ApiClient } from '@/services/api.client'
import type { Balance, Venue, OrderFormValues } from '@/types'
import { useApiCache } from './useApiCache'
import {
  computeBalanceDelta,
  applyOptimisticDelta,
  rollbackOptimistic,
  type OptimisticToken,
  type BalanceDelta,
} from '@/utils/balanceCalculations'

type UseBalancesReturn = {
  balances: Balance[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  applyOptimistic: (order: OrderFormValues, price: number) => OptimisticToken
  rollback: (token: OptimisticToken) => void
}

export function useBalances(venue?: Venue, client?: ApiClient): UseBalancesReturn {
  const apiClientRef = useRef(client || apiClient)
  const [optimisticBalances, setOptimisticBalances] = useState<Balance[] | null>(null)

  const cacheKey = useMemo(() => (venue ? `balances-${venue}` : 'balances-all'), [venue])

  const fetcher = useMemo(
    () => async () => {
      const params = venue ? { venue } : undefined
      const data = await apiClientRef.current.get<Balance[]>('/balances', { params })
      return data
    },
    [venue],
  )

  const { data, loading, error, refetch } = useApiCache<Balance[]>(
    cacheKey,
    fetcher,
    { ttl: 30000 }, // 30 seconds cache
  )

  const baseBalances = data || []

  const applyOptimistic = useCallback(
    (order: OrderFormValues, price: number): OptimisticToken => {
      const currentBalances = optimisticBalances || baseBalances
      const deltas: BalanceDelta[] = computeBalanceDelta(order, price)
      const { updatedBalances, token } = applyOptimisticDelta(
        currentBalances,
        deltas,
      )
      setOptimisticBalances(updatedBalances)
      return token
    },
    [optimisticBalances, baseBalances],
  )

  const rollback = useCallback((token: OptimisticToken) => {
    setOptimisticBalances(prev => {
      if (!prev) return null
      return rollbackOptimistic(prev, token)
    })
  }, [])

  const refresh = useCallback(async () => {
    setOptimisticBalances(null)
    await refetch()
  }, [refetch])

  return {
    balances: optimisticBalances || baseBalances,
    loading,
    error: error ? error.message || String(error) : null,
    refresh,
    applyOptimistic,
    rollback,
  }
}
