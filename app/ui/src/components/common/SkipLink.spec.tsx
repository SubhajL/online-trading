import { describe, expect, test } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SkipLink } from './SkipLink'

describe('SkipLink', () => {
  test('renders with default target and text', () => {
    render(<SkipLink />)

    const link = screen.getByText('Skip to main content')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '#main-content')
  })

  test('renders with custom target prop', () => {
    render(<SkipLink target="#content" />)

    const link = screen.getByText('Skip to main content')
    expect(link).toHaveAttribute('href', '#content')
  })

  test('renders with custom children text', () => {
    render(<SkipLink>Skip navigation</SkipLink>)

    const link = screen.getByText('Skip navigation')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '#main-content')
  })

  test('renders with both custom target and children', () => {
    render(<SkipLink target="#main">Jump to content</SkipLink>)

    const link = screen.getByText('Jump to content')
    expect(link).toHaveAttribute('href', '#main')
  })

  test('has skip-link CSS class', () => {
    render(<SkipLink />)

    const link = screen.getByText('Skip to main content')
    expect(link).toHaveClass('skip-link')
  })

  test('link is keyboard accessible', () => {
    render(<SkipLink />)

    const link = screen.getByText('Skip to main content')
    expect(link.tagName).toBe('A')
    expect(link).toHaveAttribute('href')
  })
})
