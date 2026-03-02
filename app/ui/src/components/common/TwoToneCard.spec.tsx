import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TwoToneCard } from './TwoToneCard'

describe('TwoToneCard', () => {
  it('renders title and body', () => {
    render(<TwoToneCard title="Safety & Guards">Body</TwoToneCard>)

    expect(screen.getByText('Safety & Guards')).toBeInTheDocument()
    expect(screen.getByText('Body')).toBeInTheDocument()
  })

  it('renders footer content', () => {
    render(
      <TwoToneCard title="Performance" footer={<span>REST: /dashboard/snapshot</span>}>
        Body
      </TwoToneCard>,
    )

    expect(screen.getByText('REST: /dashboard/snapshot')).toBeInTheDocument()
  })
})
