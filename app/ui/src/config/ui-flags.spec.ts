import { describe, expect, it } from 'vitest'
import { isUiRevampEnabled } from './ui-flags'

describe('isUiRevampEnabled', () => {
  it('returns true for 1', () => {
    const original = process.env.NEXT_PUBLIC_UI_REVAMP
    process.env.NEXT_PUBLIC_UI_REVAMP = '1'

    expect(isUiRevampEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_UI_REVAMP = original
  })

  it('returns true for true-like values', () => {
    const original = process.env.NEXT_PUBLIC_UI_REVAMP
    process.env.NEXT_PUBLIC_UI_REVAMP = 'true'

    expect(isUiRevampEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_UI_REVAMP = original
  })

  it('returns false by default', () => {
    const original = process.env.NEXT_PUBLIC_UI_REVAMP
    delete process.env.NEXT_PUBLIC_UI_REVAMP

    expect(isUiRevampEnabled()).toBe(false)

    process.env.NEXT_PUBLIC_UI_REVAMP = original
  })
})
