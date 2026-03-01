import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useDashboardData } from './useDashboardData'

// Mock apiClient
const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('@/services/api', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

// Mock useEmergencySell
const mockClosePositions = vi.fn()

vi.mock('./useEmergencySell', () => ({
  useEmergencySell: () => ({
    closePositions: mockClosePositions,
  }),
}))

const mockSnapshot = {
  guardStatus: {
    engineState: 'ACTIVE',
    guards: {
      drawdownGuard: { status: 'OK', blockedReason: null },
      maxPositionsGuard: { status: 'OK', blockedReason: null },
      newsGuard: { status: 'OK', blockedReason: null },
      volatilityGuard: { status: 'OK', blockedReason: null },
      correlationGuard: { status: 'OK', blockedReason: null },
    },
    overallStatus: 'OK',
    lastChecked: '2024-01-01T00:00:00Z',
  },
  exposure: {
    totalNotional: 15000,
    spotNotional: 5000,
    futuresNotional: 10000,
    unrealizedPnl: 250.75,
    realizedPnlToday: 150.25,
    totalEquity: 50000,
    availableMargin: 35000,
    marginUsagePercent: 30,
    positionCount: 3,
    spotPositionCount: 1,
    futuresPositionCount: 2,
  },
  kpis: {
    winRate: 0.65,
    profitFactor: 1.8,
    sharpeRatio: 1.2,
    maxDrawdown: 0.05,
    tradeCount: 100,
    tradingDays: 30,
    totalPnL: 5000,
    dailyPnL: 150,
  },
  equityCurve: [
    { timestamp: '2024-01-01T00:00:00Z', equity: 10000 },
    { timestamp: '2024-01-02T00:00:00Z', equity: 10100 },
  ],
  pipelineHealth: {
    symbols: [],
    lastDecision: null,
    averageLagMs: 0,
    status: 'HEALTHY',
  },
  engineStatus: {
    state: 'ACTIVE',
    autoTrading: false,
    lastDecisionAt: null,
    lastDecisionReason: null,
  },
  positions: [
    {
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      side: 'LONG',
      quantity: 0.1,
      entryPrice: 50000,
      markPrice: 51000,
      pnl: 100,
      pnlPercent: 2,
    },
  ],
  balances: [
    { asset: 'USDT', free: 10000, locked: 1000, total: 11000, venue: 'SPOT', usdValue: 11000 },
  ],
}

describe('useDashboardData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue(mockSnapshot)
    mockPost.mockResolvedValue(undefined)
  })

  describe('initial state', () => {
    it('returns all required properties', async () => {
      mockGet.mockReturnValueOnce(new Promise(() => {}))
      const { result } = renderHook(() => useDashboardData())

      // Check synchronous properties are present
      expect(result.current).toHaveProperty('guardStatus')
      expect(result.current).toHaveProperty('guardStatusLoading')
      expect(result.current).toHaveProperty('exposure')
      expect(result.current).toHaveProperty('kpis')
      expect(result.current).toHaveProperty('equityCurve')
      expect(result.current).toHaveProperty('pipelineHealth')
      expect(result.current).toHaveProperty('engineStatus')
      expect(result.current).toHaveProperty('onEmergencyClose')
      expect(result.current).toHaveProperty('positions')
      expect(result.current).toHaveProperty('balances')
      expect(result.current).toHaveProperty('refresh')
    })

    it('sets loading to true initially', () => {
      mockGet.mockReturnValueOnce(new Promise(() => {}))
      const { result } = renderHook(() => useDashboardData())

      expect(result.current.guardStatusLoading).toBe(true)
      expect(result.current.exposureLoading).toBe(true)
      expect(result.current.positionsLoading).toBe(true)
    })

    it('fetches dashboard snapshot on mount', async () => {
      renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(mockGet).toHaveBeenCalledWith('/dashboard/snapshot')
      })
    })

    it('returns guard status from API response', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatus).not.toBeNull()
      })

      expect(result.current.guardStatus?.engineState).toBe('ACTIVE')
      expect(result.current.guardStatus?.overallStatus).toBe('OK')
    })

    it('returns equity curve from API response', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.equityCurve.length).toBe(2)
      })

      expect(result.current.equityCurve[0]!.equity).toBe(10000)
    })
  })

  describe('loading states', () => {
    it('sets loading to false after fetch completes', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatusLoading).toBe(false)
      })
    })
  })

  describe('error states', () => {
    it('sets error when API call fails', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatusError).toBe('Network error')
      })
    })
  })

  describe('emergency close', () => {
    it('calls closePositions with scope and stopEngine', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatus).not.toBeNull()
      })

      await act(async () => {
        await result.current.onEmergencyClose('ALL', true, 'idem-1')
      })

      expect(mockClosePositions).toHaveBeenCalledWith({
        scope: 'ALL',
        stopEngine: true,
        idempotencyKey: 'idem-1',
      })
    })
  })

  describe('auto trading toggle', () => {
    it('calls API when auto trading is toggled', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatus).not.toBeNull()
      })

      await act(async () => {
        await result.current.onToggleAutoTrading(true)
      })

      expect(mockPost).toHaveBeenCalledWith('/trading/auto-trading', { enabled: true })
    })
  })

  describe('refresh function', () => {
    it('provides refresh function to manually refresh data', async () => {
      const { result } = renderHook(() => useDashboardData())

      await waitFor(() => {
        expect(result.current.guardStatus).not.toBeNull()
      })

      mockGet.mockClear()

      await act(async () => {
        await result.current.refresh()
      })

      expect(mockGet).toHaveBeenCalledWith('/dashboard/snapshot')
    })
  })
})
