import Link from 'next/link'
import { usePathname } from 'next/navigation'
import './Sidebar.css'

type SidebarProps = {
  isOpen?: boolean
  onToggle?: () => void
  className?: string
}

export function Sidebar({
  isOpen = true,
  onToggle,
  className = '',
}: SidebarProps) {
  const pathname = usePathname()

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/portfolio', label: 'Portfolio', icon: '💼' },
    { path: '/trades', label: 'Trades', icon: '📈' },
    { path: '/history', label: 'History', icon: '📜' },
    { path: '/analytics', label: 'Analytics', icon: '📉' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ]

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'} ${className}`}>
      {onToggle && (
        <button
          onClick={onToggle}
          className="sidebar-toggle"
          type="button"
          aria-label={isOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          {isOpen ? '◀' : '▶'}
        </button>
      )}

      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <Link
            key={item.path}
            href={item.path}
            className={`sidebar-link ${pathname === item.path ? 'active' : ''}`}
          >
            <span className="sidebar-icon">{item.icon}</span>
            {isOpen && <span className="sidebar-label">{item.label}</span>}
          </Link>
        ))}
      </nav>

      {isOpen && (
        <div className="sidebar-footer">
          <div className="connection-status">
            <span className="status-dot active" />
            <span className="status-text">Connected</span>
          </div>
          <div className="sidebar-version">v1.0.0</div>
        </div>
      )}
    </aside>
  )
}