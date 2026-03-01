'use client'

import { useState, useCallback } from 'react'
import { apiClient } from '@/services/api'
import type {
  EmergencyCloseScope,
  EmergencyCloseResult,
  EmergencyCloseResponse,
} from '@/types/dashboard'

type UseEmergencySellReturn = {
  isClosing: boolean
  error: string | null
  lastResult: EmergencyCloseResult | null
  closePositions: (args: {
    scope: EmergencyCloseScope
    stopEngine: boolean
    idempotencyKey: string
  }) => Promise<EmergencyCloseResponse>
  clearError: () => void
}

export function useEmergencySell(): UseEmergencySellReturn {
  const [isClosing, setIsClosing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<EmergencyCloseResult | null>(null)

  const closePositions = useCallback(
    async ({
      scope,
      stopEngine,
      idempotencyKey,
    }: {
      scope: EmergencyCloseScope
      stopEngine: boolean
      idempotencyKey: string
    }) => {
      setIsClosing(true)
      setError(null)

      try {
        const data = await apiClient.post<EmergencyCloseResponse>(
          '/trading/emergency-close',
          { scope, stopEngine },
          {
            headers: {
              'X-Idempotency-Key': idempotencyKey,
            },
          },
        )

        setLastResult(data)
        if (!data.success) {
          setError('Emergency close failed')
        }
        return data
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error occurred'
        setError(message)
        throw err instanceof Error ? err : new Error(message)
      } finally {
        setIsClosing(false)
      }
    },
    [],
  )

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  return {
    isClosing,
    error,
    lastResult,
    closePositions,
    clearError,
  }
}
