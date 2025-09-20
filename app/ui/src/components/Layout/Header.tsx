import Link from 'next/link'
import './Header.css'

type HeaderProps = {
  userName?: string
  onLogout?: () => void
  className?: string
}

export function Header({ userName, onLogout, className = '' }: HeaderProps) {
  return (
    <header className={`header ${className}`}>
      <div className="header-container">
        <div className="header-left">
          <Link href="/" className="header-logo">
            Trading Platform
          </Link>

          <nav className="header-nav">
            <Link href="/" className="nav-link">
              Dashboard
            </Link>
            <Link href="/portfolio" className="nav-link">
              Portfolio
            </Link>
            <Link href="/history" className="nav-link">
              History
            </Link>
            <Link href="/settings" className="nav-link">
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
