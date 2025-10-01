import type { ReactNode } from 'react'

type SkipLinkProps = {
  target?: string
  children?: ReactNode
}

/**
 * Accessible skip navigation link component.
 *
 * Renders a visually hidden link that becomes visible on keyboard focus,
 * allowing screen reader and keyboard users to bypass navigation and
 * jump directly to main content.
 *
 * @param target - Anchor target (default: '#main-content')
 * @param children - Link text (default: 'Skip to main content')
 *
 * @example
 * <SkipLink />
 * <SkipLink target="#content">Skip to content</SkipLink>
 */
export function SkipLink({ target = '#main-content', children }: SkipLinkProps) {
  return (
    <a href={target} className="skip-link">
      {children ?? 'Skip to main content'}
    </a>
  )
}
