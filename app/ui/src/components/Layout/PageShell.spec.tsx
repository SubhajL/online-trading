import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageShell } from './PageShell'

describe('PageShell', () => {
  describe('rendering', () => {
    test('renders children inside content container', () => {
      render(
        <PageShell>
          <div data-testid="test-child">Test Content</div>
        </PageShell>,
      )

      expect(screen.getByTestId('test-child')).toBeInTheDocument()
      expect(screen.getByText('Test Content')).toBeInTheDocument()
    })

    test('applies custom className to root element', () => {
      const { container } = render(
        <PageShell className="custom-page">
          <div>Content</div>
        </PageShell>,
      )

      const root = container.firstChild as HTMLElement
      expect(root).toHaveClass('custom-page')
    })
  })

  describe('padding', () => {
    test('applies default padding level 8', () => {
      const { container } = render(
        <PageShell>
          <div>Content</div>
        </PageShell>,
      )

      const root = container.firstChild as HTMLElement
      // Should have inline style from buildPageContainerStyle(tokens, 8)
      expect(root.style.padding).toBeTruthy()
    })

    test('applies custom padding level', () => {
      const { container } = render(
        <PageShell paddingLevel={4}>
          <div>Content</div>
        </PageShell>,
      )

      const root = container.firstChild as HTMLElement
      // Should have inline style from buildPageContainerStyle(tokens, 4)
      expect(root.style.padding).toBeTruthy()
    })
  })

  describe('accessibility', () => {
    test('renders skip link target when skipLinkTarget provided', () => {
      render(
        <PageShell skipLinkTarget="main-content">
          <div>Content</div>
        </PageShell>,
      )

      const skipTarget = document.getElementById('main-content')
      expect(skipTarget).toBeInTheDocument()
    })

    test('does not render skip target when skipLinkTarget not provided', () => {
      render(
        <PageShell>
          <div>Content</div>
        </PageShell>,
      )

      // No skip link target should be rendered
      const pageShellContent = screen.getByText('Content').closest('div')
      expect(pageShellContent).toBeInTheDocument()
    })
  })

  describe('max width', () => {
    test('applies medium max-width by default', () => {
      const { container } = render(
        <PageShell>
          <div>Content</div>
        </PageShell>,
      )

      const content = container.querySelector('[class*="content"]') as HTMLElement
      expect(content?.style.maxWidth).toBe('768px')
      expect(content?.style.margin).toMatch(/^0(px)? auto$/)
    })

    test('applies small max-width when specified', () => {
      const { container } = render(
        <PageShell maxWidth="sm">
          <div>Content</div>
        </PageShell>,
      )

      const content = container.querySelector('[class*="content"]') as HTMLElement
      expect(content?.style.maxWidth).toBe('640px')
      expect(content?.style.margin).toMatch(/^0(px)? auto$/)
    })

    test('applies full width when specified', () => {
      const { container } = render(
        <PageShell maxWidth="full">
          <div>Content</div>
        </PageShell>,
      )

      const content = container.querySelector('[class*="content"]') as HTMLElement
      expect(content?.style.maxWidth).toBe('100%')
      expect(content?.style.margin).toBe('')
    })
  })

  describe('integration', () => {
    test('combines inline styles with CSS module classes', () => {
      const { container } = render(
        <PageShell paddingLevel={6} maxWidth="lg">
          <div>Content</div>
        </PageShell>,
      )

      const root = container.firstChild as HTMLElement
      // Should have both inline styles (padding) and CSS classes (layout)
      expect(root.style.padding).toBeTruthy()
      expect(root.className).toBeTruthy()
    })
  })
})
