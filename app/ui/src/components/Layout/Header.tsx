'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { getNavLinkClassName, isPathActive } from '@/utils/navigation'
import './Header.css'

type HeaderProps = {
  userName?: string
  onLogout?: () => void
  className?: string
}

export function Header({ userName, onLogout, className = '' }: HeaderProps) {
  const pathname = usePathname()

  return (
    <header className={`header ${className}`}>
      <div className="header-container">
        <div className="header-left">
          <Link href="/" className="header-logo">
            Trading Platform
          </Link>

          <nav className="header-nav" aria-label="Primary navigation">
            <Link
              href="/"
              className={getNavLinkClassName(pathname, '/', 'nav-link')}
              aria-current={isPathActive(pathname, '/') ? 'page' : undefined}
            >
              Dashboard
            </Link>
            <Link
              href="/portfolio"
              className={getNavLinkClassName(pathname, '/portfolio', 'nav-link')}
              aria-current={isPathActive(pathname, '/portfolio') ? 'page' : undefined}
            >
              Portfolio
            </Link>
            <Link
              href="/history"
              className={getNavLinkClassName(pathname, '/history', 'nav-link')}
              aria-current={isPathActive(pathname, '/history') ? 'page' : undefined}
            >
              History
            </Link>
            <Link
              href="/settings"
              className={getNavLinkClassName(pathname, '/settings', 'nav-link')}
              aria-current={isPathActive(pathname, '/settings') ? 'page' : undefined}
            >
              Settings
            </Link>
          </nav>
        </div>

        <div className="header-right">
          {userName && <span className="user-name">Welcome, {userName}</span>}
          {onLogout && (
            <button onClick={onLogout} className="logout-button" type="button">
              Logout
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
