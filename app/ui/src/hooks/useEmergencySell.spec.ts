import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useEmergencySell } from './useEmergencySell'

vi.mock('@/services/api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}))

import { apiClient } from '@/services/api'

const mockApiClient = vi.mocked(apiClient)

const successResponse = {
  success: true,
  scope: 'ALL' as const,
  stopEngine: false,
  idempotencyKey: 'idem-1',
  canceledOrders: 2,
  closedPositions: 1,
  autoTradingDisabled: false,
  steps: [],
  executionTimeMs: 1,
}

describe('useEmergencySell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('starts with isClosing false', () => {
      const { result } = renderHook(() => useEmergencySell())
      expect(result.current.isClosing).toBe(false)
    })

    it('starts with no error', () => {
      const { result } = renderHook(() => useEmergencySell())
      expect(result.current.error).toBeNull()
    })

    it('starts with no lastResult', () => {
      const { result } = renderHook(() => useEmergencySell())
      expect(result.current.lastResult).toBeNull()
    })
  })

  describe('closePositions', () => {
    it('sets isClosing to true during request', async () => {
      let resolvePromise: (value: unknown) => void
      const pendingPromise = new Promise(resolve => {
        resolvePromise = resolve
      })
      mockApiClient.post.mockReturnValueOnce(pendingPromise as Promise<unknown>)

      const { result } = renderHook(() => useEmergencySell())

      act(() => {
        void result.current.closePositions({
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'idem-1',
        })
      })

      expect(result.current.isClosing).toBe(true)

      await act(async () => {
        resolvePromise!(successResponse)
      })
    })

    it('calls apiClient.post with body and X-Idempotency-Key header', async () => {
      mockApiClient.post.mockResolvedValueOnce(successResponse)

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions({
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'idem-1',
        })
      })

      expect(mockApiClient.post).toHaveBeenCalledWith(
        '/trading/emergency-close',
        { scope: 'ALL', stopEngine: false },
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Idempotency-Key': 'idem-1',
          }),
        }),
      )
    })

    it('sets lastResult on success and returns response', async () => {
      mockApiClient.post.mockResolvedValueOnce(successResponse)

      const { result } = renderHook(() => useEmergencySell())

      let returned: unknown
      await act(async () => {
        returned = await result.current.closePositions({
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'idem-1',
        })
      })

      expect(result.current.lastResult).toEqual(successResponse)
      expect(returned).toEqual(successResponse)
    })

    it('sets lastResult and error on unsuccessful response and returns response', async () => {
      const failedResponse = { ...successResponse, success: false }
      mockApiClient.post.mockResolvedValueOnce(failedResponse)

      const { result } = renderHook(() => useEmergencySell())

      let returned: unknown
      await act(async () => {
        returned = await result.current.closePositions({
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'idem-1',
        })
      })

      expect(result.current.lastResult).toEqual(failedResponse)
      expect(result.current.error).toBe('Emergency close failed')
      expect(returned).toEqual(failedResponse)
    })

    it('sets error on network failure and throws', async () => {
      mockApiClient.post.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await expect(
          result.current.closePositions({
            scope: 'ALL',
            stopEngine: false,
            idempotencyKey: 'idem-1',
          }),
        ).rejects.toThrow('Network error')
      })

      await waitFor(() => {
        expect(result.current.error).toBe('Network error')
      })
    })

    it('clears isClosing when request completes', async () => {
      mockApiClient.post.mockResolvedValueOnce(successResponse)

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions({
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'idem-1',
        })
      })

      expect(result.current.isClosing).toBe(false)
    })
  })

  describe('clearError', () => {
    it('clears the error state', async () => {
      mockApiClient.post.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        try {
          await result.current.closePositions({
            scope: 'ALL',
            stopEngine: false,
            idempotencyKey: 'idem-1',
          })
        } catch {
          // expected
        }
      })

      await waitFor(() => {
        expect(result.current.error).toBe('Network error')
      })

      act(() => {
        result.current.clearError()
      })

      expect(result.current.error).toBeNull()
    })
  })
})
