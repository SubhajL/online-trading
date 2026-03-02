import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BusBar } from './BusBar'

describe('BusBar', () => {
  it('renders all node labels', () => {
    render(<BusBar nodes={['API', 'RMS', 'EXEC']} activeCount={2} />)

    expect(screen.getByText('API')).toBeInTheDocument()
    expect(screen.getByText('RMS')).toBeInTheDocument()
    expect(screen.getByText('EXEC')).toBeInTheDocument()
  })
})
