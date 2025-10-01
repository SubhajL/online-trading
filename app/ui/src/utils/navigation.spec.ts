import { describe, expect, test } from 'vitest'
import { isPathActive, getNavLinkClassName } from './navigation'

describe('isPathActive', () => {
  test('returns true for exact root path match', () => {
    expect(isPathActive('/', '/')).toBe(true)
  })

  test('returns false when on non-root path', () => {
    expect(isPathActive('/portfolio', '/')).toBe(false)
  })

  test('returns true for exact path match', () => {
    expect(isPathActive('/history', '/history')).toBe(true)
  })

  test('returns true for nested route under path', () => {
    expect(isPathActive('/history/details', '/history')).toBe(true)
  })

  test('returns false for similar but different paths', () => {
    expect(isPathActive('/history-old', '/history')).toBe(false)
  })

  test('handles null pathname safely', () => {
    expect(isPathActive(null, '/history')).toBe(false)
  })

  test('handles undefined pathname safely', () => {
    expect(isPathActive(undefined, '/history')).toBe(false)
  })
})

describe('getNavLinkClassName', () => {
  test('adds active class when path matches', () => {
    const result = getNavLinkClassName('/history', '/history', 'nav-link')
    expect(result).toBe('nav-link active')
  })

  test('omits active class when path differs', () => {
    const result = getNavLinkClassName('/portfolio', '/history', 'nav-link')
    expect(result).toBe('nav-link')
  })

  test('handles root path correctly', () => {
    const result = getNavLinkClassName('/', '/', 'nav-link')
    expect(result).toBe('nav-link active')
  })

  test('handles null pathname gracefully', () => {
    const result = getNavLinkClassName(null, '/history', 'nav-link')
    expect(result).toBe('nav-link')
  })
})
