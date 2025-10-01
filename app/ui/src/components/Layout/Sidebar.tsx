'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Briefcase,
  TrendingUp,
  History,
  BarChart3,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { isPathActive } from '@/utils/navigation'
import './Sidebar.css'

type SidebarProps = {
  isOpen?: boolean
  onToggle?: () => void
  className?: string
}

export function Sidebar({ isOpen = true, onToggle, className = '' }: SidebarProps) {
  const pathname = usePathname()

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/portfolio', label: 'Portfolio', icon: Briefcase },
    { path: '/trades', label: 'Trades', icon: TrendingUp },
    { path: '/history', label: 'History', icon: History },
    { path: '/analytics', label: 'Analytics', icon: BarChart3 },
    { path: '/settings', label: 'Settings', icon: Settings },
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
          {isOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      )}

      <nav className="sidebar-nav" aria-label="Main navigation">
        {menuItems.map(item => {
          const Icon = item.icon
          const active = isPathActive(pathname, item.path)
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`sidebar-link ${active ? 'active' : ''}`}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              title={!isOpen ? item.label : undefined}
            >
              <Icon className="sidebar-icon" size={20} aria-hidden="true" />
              {isOpen && <span className="sidebar-label">{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {isOpen && (
        <div className="sidebar-footer">
          <div className="connection-status">
            <span className="status-dot active" aria-label="Connected" />
            <span className="status-text">Connected</span>
          </div>
          <div className="sidebar-version">v1.0.0</div>
        </div>
      )}
    </aside>
  )
}
