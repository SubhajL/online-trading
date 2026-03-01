import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('sonner', async () => {
  const actual = await vi.importActual('sonner')
  return {
    ...actual,
    toast: Object.assign(vi.fn(), {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    }),
  }
})

vi.mock('@/components/ui/sonner', () => ({
  Toaster: (props: Record<string, unknown>) => (
    <div
      data-testid="toaster"
      data-position={props.position}
      data-rich-colors={String(props.richColors)}
      data-close-button={String(props.closeButton)}
    />
  ),
}))

import { ToastStack, showTradeToast } from './ToastStack'
import { toast } from 'sonner'

describe('ToastStack', () => {
  it('renders Toaster with trading defaults', () => {
    render(<ToastStack />)

    const toaster = screen.getByTestId('toaster')
    expect(toaster).toHaveAttribute('data-position', 'bottom-right')
    expect(toaster).toHaveAttribute('data-rich-colors', 'true')
    expect(toaster).toHaveAttribute('data-close-button', 'true')
  })
})

describe('showTradeToast', () => {
  it('calls toast.success for success type', () => {
    showTradeToast('success', 'Order filled', 'BTC 0.01')

    expect(toast.success).toHaveBeenCalledWith('Order filled', {
      description: 'BTC 0.01',
    })
  })

  it('calls toast.error for error type', () => {
    showTradeToast('error', 'Order rejected')

    expect(toast.error).toHaveBeenCalledWith('Order rejected', {
      description: undefined,
    })
  })

  it('calls toast.warning for warning type', () => {
    showTradeToast('warning', 'High slippage')

    expect(toast.warning).toHaveBeenCalledWith('High slippage', {
      description: undefined,
    })
  })

  it('calls toast.info for info type', () => {
    showTradeToast('info', 'Market open')

    expect(toast.info).toHaveBeenCalledWith('Market open', {
      description: undefined,
    })
  })
})
