import { describe, expect, it } from 'vitest'

import { cn } from './utils'

describe('cn', () => {
  it('merges class name inputs', () => {
    expect(cn('alpha', undefined, 'beta')).toBe('alpha beta')
  })

  it('drops falsy values and merges arrays', () => {
    expect(cn(['alpha', false, 'beta'], null, 'gamma')).toBe('alpha beta gamma')
  })
})
