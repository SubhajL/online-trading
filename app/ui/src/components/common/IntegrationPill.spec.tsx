import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { IntegrationPill } from './IntegrationPill'

describe('IntegrationPill', () => {
  it('renders transport and endpoint', () => {
    render(<IntegrationPill transport="REST" endpoint="/dashboard/snapshot" />)

    expect(screen.getByLabelText('REST: /dashboard/snapshot')).toBeInTheDocument()
    expect(screen.getByText('/dashboard/snapshot')).toBeInTheDocument()
  })
})
