import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '@/services/api'
import type { RouterSoakStatus } from '@/types/soak'

const POLL_INTERVAL_MS = 5000

type UseSoakResult = {
  status: RouterSoakStatus | null
  loading: boolean
  error: string | null
  refresh: () => void
}

// Polls the BFF's read-only router soak status. Readiness has no WebSocket
// event and the reconcile summary is a passive snapshot, so a short REST
// poll is the right transport.
export function useSoak(): UseSoakResult {
  const [status, setStatus] = useState<RouterSoakStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiClient.get<RouterSoakStatus>('/soak/status')
      setStatus(data)
      setError(null)
    } catch (err) {
      // Keep the last-good snapshot in `status`; surface the failure via
      // `error` so the panel can show a stale banner rather than blanking
      // the operational view on a single failed poll.
      setError(err instanceof Error ? err.message : 'Failed to fetch soak status')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  useEffect(() => {
    const interval = setInterval(fetchStatus, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchStatus])

  return { status, loading, error, refresh: fetchStatus }
}
