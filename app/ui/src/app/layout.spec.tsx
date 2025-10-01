import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import RootLayout from './layout'

vi.mock('next/font/google', () => ({
  Inter: () => ({ className: 'inter-font' }),
}))

describe('RootLayout', () => {
  test('skip link is present in DOM', () => {
    render(
      <RootLayout>
        <main id="main-content">Test Content</main>
      </RootLayout>,
    )

    const skipLink = screen.getByText('Skip to main content')
    expect(skipLink).toBeInTheDocument()
  })

  test('skip link points to main content', () => {
    render(
      <RootLayout>
        <main id="main-content">Test Content</main>
      </RootLayout>,
    )

    const skipLink = screen.getByText('Skip to main content')
    expect(skipLink).toHaveAttribute('href', '#main-content')
  })

  test('skip link has correct styling class', () => {
    render(
      <RootLayout>
        <main id="main-content">Test Content</main>
      </RootLayout>,
    )

    const skipLink = screen.getByText('Skip to main content')
    expect(skipLink).toHaveClass('skip-link')
  })

  test('renders children correctly', () => {
    render(
      <RootLayout>
        <div data-testid="test-child">Child Content</div>
      </RootLayout>,
    )

    expect(screen.getByTestId('test-child')).toBeInTheDocument()
  })
})
