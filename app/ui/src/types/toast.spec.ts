import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  createToastId,
  createToast,
  getToastTestId,
  TOAST_AUTO_DISMISS_MS,
  TOAST_MAX_VISIBLE,
} from './toast'
import type { ToastInput, ToastType } from './toast'

describe('toast types', () => {
  describe('createToastId', () => {
    it('returns a unique string id', () => {
      const id1 = createToastId()
      const id2 = createToastId()

      expect(typeof id1).toBe('string')
      expect(id1).not.toBe(id2)
    })

    it('returns valid UUID format', () => {
      const id = createToastId()
      const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

      expect(id).toMatch(uuidRegex)
    })
  })

  describe('createToast', () => {
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2025-01-15T10:00:00Z'))
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('creates toast with success type', () => {
      const input: ToastInput = { type: 'success', message: 'Order placed successfully' }
      const toast = createToast(input)

      expect(toast.type).toBe('success')
      expect(toast.message).toBe('Order placed successfully')
      expect(toast.createdAt).toBe(Date.now())
      expect(typeof toast.id).toBe('string')
    })

    it('creates toast with error type', () => {
      const input: ToastInput = { type: 'error', message: 'Order failed' }
      const toast = createToast(input)

      expect(toast.type).toBe('error')
      expect(toast.message).toBe('Order failed')
    })

    it('creates toast with info type', () => {
      const input: ToastInput = { type: 'info', message: 'Processing order' }
      const toast = createToast(input)

      expect(toast.type).toBe('info')
      expect(toast.message).toBe('Processing order')
    })

    it('generates unique id for each toast', () => {
      const input: ToastInput = { type: 'success', message: 'Test' }
      const toast1 = createToast(input)
      const toast2 = createToast(input)

      expect(toast1.id).not.toBe(toast2.id)
    })
  })

  describe('getToastTestId', () => {
    const testCases: { type: ToastType; expected: string }[] = [
      { type: 'success', expected: 'order-success' },
      { type: 'error', expected: 'order-error' },
      { type: 'info', expected: 'order-info' },
    ]

    it.each(testCases)('returns "$expected" for type "$type"', ({ type, expected }) => {
      expect(getToastTestId(type)).toBe(expected)
    })
  })

  describe('constants', () => {
    it('TOAST_AUTO_DISMISS_MS is 5000ms', () => {
      expect(TOAST_AUTO_DISMISS_MS).toBe(5000)
    })

    it('TOAST_MAX_VISIBLE is 3', () => {
      expect(TOAST_MAX_VISIBLE).toBe(3)
    })
  })
})
