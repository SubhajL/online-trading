import { describe, expect, test } from 'vitest'
import { mapStatusToClassName } from './cssHelpers'

describe('mapStatusToClassName', () => {
  test('converts NEW to statusNew', () => {
    expect(mapStatusToClassName('NEW')).toBe('statusNew')
  })

  test('converts FILLED to statusFilled', () => {
    expect(mapStatusToClassName('FILLED')).toBe('statusFilled')
  })

  test('converts PARTIALLY_FILLED to statusPartiallyFilled', () => {
    expect(mapStatusToClassName('PARTIALLY_FILLED')).toBe('statusPartiallyFilled')
  })

  test('converts CANCELED to statusCanceled', () => {
    expect(mapStatusToClassName('CANCELED')).toBe('statusCanceled')
  })

  test('converts REJECTED to statusRejected', () => {
    expect(mapStatusToClassName('REJECTED')).toBe('statusRejected')
  })

  test('converts EXPIRED to statusExpired', () => {
    expect(mapStatusToClassName('EXPIRED')).toBe('statusExpired')
  })

  test('handles empty string', () => {
    expect(mapStatusToClassName('')).toBe('status')
  })
})
