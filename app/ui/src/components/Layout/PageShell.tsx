import type { ReactNode } from 'react'
import { useMemo } from 'react'
import { getTokens } from '@/utils/getTokens'
import { buildPageContainerStyle } from '@/utils/stylingHelpers'
import styles from './PageShell.module.css'

type PageShellProps = {
  children: ReactNode
  paddingLevel?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10
  skipLinkTarget?: string
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
  className?: string
}

/**
 * Reusable page wrapper providing consistent structure with token-based styling.
 * Includes skip-link support for accessibility and responsive max-width containers.
 *
 * @param children - Page content to render
 * @param paddingLevel - Spacing level (0-10) from token system, defaults to 8
 * @param skipLinkTarget - Optional ID for skip-link anchor target
 * @param maxWidth - Maximum content width: sm (640px), md (768px), lg (1024px), xl (1280px), full (100%)
 * @param className - Additional CSS classes for the root element
 */
export function PageShell({
  children,
  paddingLevel = 8,
  skipLinkTarget,
  maxWidth = 'md',
  className = '',
}: PageShellProps) {
  const tokens = useMemo(() => getTokens(), [])
  const containerStyles = buildPageContainerStyle(tokens, paddingLevel)
  const contentStyles = buildPageContainerStyle(tokens, 0, maxWidth)

  return (
    <div className={`${styles.pageShell} ${className}`} style={containerStyles}>
      {skipLinkTarget && <div id={skipLinkTarget} className={styles.skipTarget} tabIndex={-1} />}
      <div
        className={styles.content}
        style={{
          maxWidth: contentStyles.maxWidth,
          margin: contentStyles.margin,
        }}
      >
        {children}
      </div>
    </div>
  )
}
