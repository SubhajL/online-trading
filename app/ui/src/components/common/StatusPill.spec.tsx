import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('renders connected state label', () => {
    render(<StatusPill state="connected" />)
    expect(screen.getByRole('status', { name: 'Connected' })).toBeInTheDocument()
  })

  it('renders offline state label', () => {
    render(<StatusPill state="offline" />)
    expect(screen.getByRole('status', { name: 'Offline' })).toBeInTheDocument()
  })
})
