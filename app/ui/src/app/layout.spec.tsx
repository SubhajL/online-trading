import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import RootLayout from './layout'

vi.mock('next/font/google', () => ({
  Inter: () => ({ className: 'inter-font', variable: '--font-sans' }),
  JetBrains_Mono: () => ({ className: 'jetbrains-mono-font', variable: '--font-mono' }),
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

  test('applies both Inter and JetBrains Mono font variables', () => {
    const { container } = render(
      <RootLayout>
        <main id="main-content">Test Content</main>
      </RootLayout>,
    )

    const body = container.querySelector('body')
    expect(body).toHaveClass('font-sans')
    expect(body?.className).toContain('--font-sans')
    expect(body?.className).toContain('--font-mono')
  })
})
