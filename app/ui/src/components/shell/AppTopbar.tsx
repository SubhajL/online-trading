'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import { StatusPill } from '@/components/common/StatusPill'
import { ThemeToggle } from './ThemeToggle'
import { isPathActive } from '@/utils/navigation'

type ConnectionState = 'connected' | 'reconnecting' | 'offline'

type AppTopbarProps = {
  onMenuClick?: () => void
  onAlertsClick?: () => void
  onHelpClick?: () => void
  onCommandPaletteClick?: () => void
  onLogout?: () => void
  connectionState?: ConnectionState
  unreadAlerts?: number
  userEmail?: string
  showMenuButton?: boolean
  variant?: 'default' | 'revamp'
}

const CONNECTION_CONFIG = {
  connected: {
    icon: 'wifi',
    label: 'Connected',
    className: 'text-green-500 border-green-500/30 bg-green-500/10',
  },
  reconnecting: {
    icon: 'progress_activity',
    label: 'Reconnecting',
    className: 'text-yellow-500 border-yellow-500/30 bg-yellow-500/10',
  },
  offline: {
    icon: 'wifi_off',
    label: 'Offline',
    className: 'text-red-500 border-red-500/30 bg-red-500/10',
  },
} as const

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: 'dashboard' },
  { path: '/trades', label: 'Trades', icon: 'candlestick_chart' },
  { path: '/portfolio', label: 'Portfolio', icon: 'work' },
  { path: '/history', label: 'History', icon: 'history' },
  { path: '/analytics', label: 'Analytics', icon: 'bar_chart' },
  { path: '/settings', label: 'Settings', icon: 'settings' },
] as const

function ConnectionPill({ state }: { state: ConnectionState }) {
  const { icon, label, className } = CONNECTION_CONFIG[state]

  return (
    <Badge
      variant="outline"
      className={cn('gap-1.5 text-xs font-normal', className)}
      role="status"
      aria-label={`Connection status: ${label}`}
    >
      <MaterialIcon
        name={icon}
        size="sm"
        className={cn(state === 'reconnecting' && 'animate-spin')}
      />
      <span className="hidden lg:inline">{label}</span>
    </Badge>
  )
}

function NavLinks() {
  const pathname = usePathname()

  return (
    <nav className="hidden lg:flex items-center gap-1" aria-label="Main navigation">
      {NAV_ITEMS.map(item => {
        const active = isPathActive(pathname, item.path)
        return (
          <Link
            key={item.path}
            href={item.path}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
              active
                ? 'bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white',
            )}
            aria-current={active ? 'page' : undefined}
          >
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}

export function AppTopbar({
  onMenuClick,
  onAlertsClick,
  onHelpClick,
  onCommandPaletteClick,
  onLogout,
  connectionState = 'connected',
  unreadAlerts = 0,
  userEmail,
  showMenuButton = false,
  variant = 'default',
}: AppTopbarProps) {
  const revamp = variant === 'revamp'

  return (
    <header
      data-testid="app-topbar"
      className={cn(
        'sticky top-0 z-20 flex h-18 items-center gap-4 px-4 lg:px-6 shadow-sm',
        revamp
          ? 'border-b border-[#232348] bg-[#1A1A2E] text-white'
          : 'border-b border-slate-100 bg-white text-slate-900 dark:border-border-dark-mode dark:bg-surface-dark dark:text-white',
      )}
    >
      {/* Left cluster: Logo + Search */}
      <div className="flex items-center gap-4">
        {showMenuButton && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onMenuClick}
            aria-label="Open menu"
            className="lg:hidden h-9 w-9"
          >
            <MaterialIcon name="menu" size="md" />
          </Button>
        )}
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <div className="h-8 w-8 bg-indigo-50 dark:bg-primary/10 rounded-lg flex items-center justify-center text-indigo-500 dark:text-primary">
            <MaterialIcon name="candlestick_chart" size="md" />
          </div>
          <span className="text-lg font-bold tracking-tight hidden sm:inline">Online Trader</span>
        </Link>

        {/* Search input (visible md+) */}
        <div className="hidden md:flex relative">
          <MaterialIcon
            name="search"
            size="md"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <Input
            type="search"
            placeholder={revamp ? 'Search symbols, orders, or commands...' : 'Search...'}
            className={cn(
              'h-9 w-48 pl-10 pr-16 lg:w-64',
              revamp
                ? 'rounded-xl border-[#323267] bg-[#111122] text-slate-200 placeholder:text-slate-500'
                : 'rounded-lg border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
            )}
            aria-label="Search"
          />
          {revamp && (
            <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-slate-700 bg-[#15152a] px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
              Ctrl+K
            </kbd>
          )}
        </div>
      </div>

      {/* Center: Navigation links (visible lg+) */}
      <div className="flex-1 flex justify-center">{!revamp && <NavLinks />}</div>

      {/* Right cluster: Actions + User */}
      <div className="flex items-center gap-1">
        <TooltipProvider delayDuration={300}>
          {revamp ? (
            <StatusPill state={connectionState} />
          ) : (
            <ConnectionPill state={connectionState} />
          )}
          <ThemeToggle />

          {/* Alerts bell */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onAlertsClick}
                aria-label={unreadAlerts > 0 ? `${unreadAlerts} unread alerts` : 'Alerts'}
                className="relative h-9 w-9"
              >
                <MaterialIcon name="notifications" size="md" />
                {unreadAlerts > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
                    {unreadAlerts > 99 ? '99+' : unreadAlerts}
                  </span>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Alerts</TooltipContent>
          </Tooltip>

          {/* Help */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onHelpClick}
                aria-label="Help"
                className="h-9 w-9"
              >
                <MaterialIcon name="help" size="md" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Help</TooltipContent>
          </Tooltip>

          {/* Command palette */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onCommandPaletteClick}
                aria-label="Command palette (Ctrl+K)"
                className="h-9 w-9"
              >
                <MaterialIcon name="terminal" size="md" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Command Palette <kbd className="ml-1 rounded bg-slate-100 px-1 text-[10px]">⌘K</kbd>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* User menu with pill border styling */}
        {userEmail && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="ml-2 gap-2 text-xs rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 h-9"
              >
                <span className="hidden lg:inline max-w-[120px] truncate text-slate-600 dark:text-slate-300">
                  {userEmail}
                </span>
                <span className="h-6 w-6 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                  {userEmail[0]?.toUpperCase()}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem disabled className="text-xs text-slate-400">
                {userEmail}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onLogout} className="text-red-400">
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  )
}
