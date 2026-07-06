import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RouterSoakPanel } from './RouterSoakPanel'
import type { RouterSoakStatus } from '@/types/soak'

const createStatus = (overrides: Partial<RouterSoakStatus> = {}): RouterSoakStatus => ({
  readiness: { ready: true, status: 'ready' },
  reconcile: {
    hasRun: true,
    lastRunAt: '2026-07-06T00:00:00Z',
    summary: {
      bracketsSwept: 4,
      entriesChecked: 2,
      legsResolved: 1,
      exitLegsUpdated: 3,
      bracketsClosed: 1,
      staleReserved: 0,
      unrepairedLegs: 0,
      errors: 0,
    },
  },
  checkedAt: '2026-07-06T00:00:05Z',
  ...overrides,
})

describe('RouterSoakPanel', () => {
  it('renders the loading skeleton while loading', () => {
    render(<RouterSoakPanel status={null} loading />)
    expect(screen.getByTestId('soak-panel-loading')).toBeInTheDocument()
  })

  it('renders the full error card only when there is no last-good data', () => {
    render(<RouterSoakPanel status={null} error="router down" />)
    expect(screen.getByTestId('soak-panel-error')).toBeInTheDocument()
    expect(screen.getByText(/router down/)).toBeInTheDocument()
  })

  it('keeps the last-good snapshot with a stale banner when a refresh fails', () => {
    render(<RouterSoakPanel status={createStatus()} error="network blip" />)
    // Data panel still shown, not the error card
    expect(screen.getByTestId('soak-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('soak-panel-error')).not.toBeInTheDocument()
    expect(screen.getByTestId('soak-stale-banner')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
  })

  it('shows a green Ready badge when the router is ready', () => {
    render(<RouterSoakPanel status={createStatus()} />)
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByTestId('readiness-indicator')).toHaveClass('bg-success')
  })

  it('shows Reconciling while the readiness gate is held', () => {
    render(
      <RouterSoakPanel
        status={createStatus({ readiness: { ready: false, status: 'reconciling' } })}
      />,
    )
    expect(screen.getByText('Reconciling')).toBeInTheDocument()
    expect(screen.getByTestId('readiness-indicator')).toHaveClass('bg-warning')
  })

  it('shows Unreachable when the router cannot be reached', () => {
    render(
      <RouterSoakPanel
        status={createStatus({
          readiness: { ready: false, status: 'unreachable', error: 'ECONNREFUSED' },
        })}
      />,
    )
    expect(screen.getByText('Unreachable')).toBeInTheDocument()
    expect(screen.getByTestId('readiness-indicator')).toHaveClass('bg-destructive')
    expect(screen.getByTestId('readiness-error')).toHaveTextContent('ECONNREFUSED')
  })

  it('renders reconcile counters with unrepaired/errors highlighted when non-zero', () => {
    render(
      <RouterSoakPanel
        status={createStatus({
          reconcile: {
            hasRun: true,
            summary: {
              bracketsSwept: 5,
              entriesChecked: 0,
              legsResolved: 0,
              exitLegsUpdated: 0,
              bracketsClosed: 0,
              staleReserved: 0,
              unrepairedLegs: 2,
              errors: 1,
            },
          },
        })}
      />,
    )
    expect(screen.getByTestId('counter-value-bracketsSwept')).toHaveTextContent('5')
    expect(screen.getByTestId('counter-value-unrepairedLegs')).toHaveClass('text-destructive')
    expect(screen.getByTestId('counter-value-errors')).toHaveClass('text-destructive')
    // A zero alarm counter is not highlighted
    expect(screen.getByTestId('counter-value-bracketsSwept')).not.toHaveClass('text-destructive')
  })

  it('shows a "no reconcile pass yet" note before the first pass', () => {
    render(<RouterSoakPanel status={createStatus({ reconcile: { hasRun: false } })} />)
    expect(screen.getByTestId('reconcile-none')).toBeInTheDocument()
  })

  it('shows an unavailable note when reconcile status could not be fetched', () => {
    render(
      <RouterSoakPanel
        status={createStatus({ reconcile: { hasRun: false, unavailable: true } })}
      />,
    )
    expect(screen.getByTestId('reconcile-unavailable')).toBeInTheDocument()
  })
})
