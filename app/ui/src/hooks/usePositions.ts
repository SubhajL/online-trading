import { useMemo, useRef, useEffect, useState } from 'react'
import { apiClient } from '@/services/api'
import type { ApiClient } from '@/services/api.client'
import type { Position, Venue } from '@/types'
import { useApiCache } from './useApiCache'
import { websocketService } from '@/services/websocket'

type BffPosition = {
  symbol: Position['symbol']
  side: Position['side']
  quantity: number
  entryPrice: number
  currentPrice: number
  pnl: number
  pnlPercent: number
  venue: Venue
  timestamp?: number
}

type UsePositionsReturn = {
  positions: Position[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  totalValue: number
  totalPnl: number
  positionsByVenue: Record<Venue, Position[]>
}

function toUiPosition(position: BffPosition | Position): Position {
  if ('markPrice' in position) {
    return position
  }

  return {
    symbol: position.symbol,
    side: position.side,
    quantity: position.quantity,
    entryPrice: position.entryPrice,
    markPrice: position.currentPrice,
    pnl: position.pnl,
    pnlPercent: position.pnlPercent,
    venue: position.venue,
  }
}

export function usePositions(venue?: Venue, client?: ApiClient): UsePositionsReturn {
  const apiClientRef = useRef(client || apiClient)
  const [wsPositions, setWsPositions] = useState<Map<string, Position>>(new Map())

  const cacheKey = useMemo(() => (venue ? `positions-${venue}` : 'positions-all'), [venue])

  const fetcher = useMemo(
    () => async () => {
      const params = venue ? { venue } : undefined
      const data = await apiClientRef.current.get<BffPosition[]>('/trading/positions', {
        params,
      })
      return data.map(toUiPosition)
    },
    [venue],
  )

  const { data, loading, error, refetch } = useApiCache<Position[]>(
    cacheKey,
    fetcher,
    { ttl: 10000 }, // 10 seconds cache for positions
  )

  // Subscribe to WebSocket position updates
  useEffect(() => {
    let unsubscribe = () => {}
    try {
      unsubscribe = websocketService.subscribe(
        'position_update.v1',
        (position: Position | BffPosition | null | undefined) => {
          if (!position) {
            return
          }

          const normalizedPosition = toUiPosition(position)
          setWsPositions(prev => {
            const updated = new Map(prev)
            const key = `${normalizedPosition.symbol}-${normalizedPosition.venue}`

            // If venue filter is active, only update matching positions
            if (!venue || normalizedPosition.venue === venue) {
              updated.set(key, normalizedPosition)
            }

            return updated
          })
        },
      )
    } catch {
      // Fail-open: websocket may not be initialized yet.
    }

    return () => {
      unsubscribe()
    }
  }, [venue])

  // Merge REST and WebSocket positions
  const positions = useMemo(() => {
    if (!data) return []

    // Create a map of REST positions
    const positionMap = new Map<string, Position>()
    data.forEach(pos => {
      const key = `${pos.symbol}-${pos.venue}`
      positionMap.set(key, pos)
    })

    // Override with WebSocket updates
    wsPositions.forEach((wsPos, key) => {
      positionMap.set(key, wsPos)
    })

    return Array.from(positionMap.values())
  }, [data, wsPositions])

  // Calculate total portfolio value
  const totalValue = useMemo(
    () => positions.reduce((sum, pos) => sum + pos.quantity * pos.markPrice, 0),
    [positions],
  )

  // Calculate total PnL
  const totalPnl = useMemo(() => positions.reduce((sum, pos) => sum + pos.pnl, 0), [positions])

  // Group positions by venue
  const positionsByVenue = useMemo(() => {
    const grouped: Record<Venue, Position[]> = {
      SPOT: [],
      USD_M: [],
    }

    positions.forEach(position => {
      grouped[position.venue].push(position)
    })

    return grouped
  }, [positions])

  return {
    positions,
    loading,
    error: error?.message || null,
    refresh: async () => {
      await refetch()
    },
    totalValue,
    totalPnl,
    positionsByVenue,
  }
}
