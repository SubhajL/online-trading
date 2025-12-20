'use client'

import { useState, useCallback } from 'react'
import type { EmergencyCloseScope, EmergencyCloseResult } from '@/types/dashboard'

type UseEmergencySellReturn = {
  isClosing: boolean
  error: string | null
  lastResult: EmergencyCloseResult | null
  closePositions: (scope: EmergencyCloseScope) => Promise<void>
  clearError: () => void
}

function generateIdempotencyKey(): string {
  return `emergency-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
}

export function useEmergencySell(): UseEmergencySellReturn {
  const [isClosing, setIsClosing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<EmergencyCloseResult | null>(null)

  const closePositions = useCallback(async (scope: EmergencyCloseScope) => {
    setIsClosing(true)
    setError(null)

    const idempotencyKey = generateIdempotencyKey()

    try {
      const response = await fetch('/api/trading/emergency-close', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({ scope }),
      })

      const data = await response.json()

      if (!response.ok) {
        setError(data.error || `Failed with status ${response.status}`)
        return
      }

      setLastResult({
        success: data.success,
        closedCount: data.closedCount,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
    } finally {
      setIsClosing(false)
    }
  }, [])

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
