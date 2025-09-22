import { useState, useEffect } from 'react'
import { apiClient } from '@/services/api'
import type { Balance, Venue } from '@/types'

type UseBalancesReturn = {
  balances: Balance[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useBalances(venue?: Venue): UseBalancesReturn {
  const [balances, setBalances] = useState<Balance[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchBalances = async () => {
    try {
      setLoading(true)
      setError(null)

      const params = venue ? { venue } : undefined
      const data = await apiClient.get<{ balances: Balance[] }>('/balances', { params })
      setBalances(data.balances)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch balances')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchBalances()
  }, [venue])

  return {
    balances,
    loading,
    error,
    refresh: fetchBalances,
  }
}
