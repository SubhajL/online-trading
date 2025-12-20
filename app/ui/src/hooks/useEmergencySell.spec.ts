import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useEmergencySell } from './useEmergencySell'
import type { EmergencyCloseScope } from '@/types/dashboard'

const mockFetch = vi.fn()

describe('useEmergencySell', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    mockFetch.mockReset()
  })

  describe('initial state', () => {
    it('starts with isClosing false', () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) })
      const { result } = renderHook(() => useEmergencySell())

      expect(result.current.isClosing).toBe(false)
    })

    it('starts with no error', () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) })
      const { result } = renderHook(() => useEmergencySell())

      expect(result.current.error).toBeNull()
    })

    it('starts with no lastResult', () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) })
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
      mockFetch.mockReturnValueOnce(pendingPromise)

      const { result } = renderHook(() => useEmergencySell())

      act(() => {
        result.current.closePositions('ALL')
      })

      expect(result.current.isClosing).toBe(true)

      await act(async () => {
        resolvePromise!({ ok: true, json: async () => ({ success: true }) })
      })
    })

    it('calls API with correct scope for ALL', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, closedCount: 3 }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toBe('/api/trading/emergency-close')
      expect(options.method).toBe('POST')
      expect(options.headers['Content-Type']).toBe('application/json')
      expect(options.body).toBe(JSON.stringify({ scope: 'ALL' }))
    })

    it('calls API with correct scope for SPOT', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, closedCount: 1 }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('SPOT')
      })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [, options] = mockFetch.mock.calls[0]
      expect(options.body).toBe(JSON.stringify({ scope: 'SPOT' }))
    })

    it('calls API with correct scope for FUTURES', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, closedCount: 2 }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('FUTURES')
      })

      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [, options] = mockFetch.mock.calls[0]
      expect(options.body).toBe(JSON.stringify({ scope: 'FUTURES' }))
    })

    it('sets lastResult on successful close', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, closedCount: 3 }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(result.current.lastResult).toEqual({
        success: true,
        closedCount: 3,
      })
    })

    it('sets error on failed close', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal server error' }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(result.current.error).toBe('Internal server error')
    })

    it('sets error on network failure', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(result.current.error).toBe('Network error')
    })

    it('resets isClosing to false after request completes', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(result.current.isClosing).toBe(false)
    })
  })

  describe('clearError', () => {
    it('clears the error state', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      expect(result.current.error).toBe('Network error')

      act(() => {
        result.current.clearError()
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('idempotency', () => {
    it('generates unique idempotency key for each request', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      })

      const { result } = renderHook(() => useEmergencySell())

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      const firstCall = mockFetch.mock.calls[0]
      const firstHeaders = firstCall[1].headers

      await act(async () => {
        await result.current.closePositions('ALL')
      })

      const secondCall = mockFetch.mock.calls[1]
      const secondHeaders = secondCall[1].headers

      expect(firstHeaders['X-Idempotency-Key']).toBeDefined()
      expect(secondHeaders['X-Idempotency-Key']).toBeDefined()
      expect(firstHeaders['X-Idempotency-Key']).not.toBe(secondHeaders['X-Idempotency-Key'])
    })
  })
})
