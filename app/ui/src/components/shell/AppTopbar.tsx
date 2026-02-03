'use client'

import { Menu, Bell, HelpCircle, Terminal, Wifi, WifiOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

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
}

function ConnectionPill({ state }: { state: ConnectionState }) {
  const config = {
    connected: {
      icon: Wifi,
      label: 'Connected',
      className: 'text-green-500 border-green-500/30 bg-green-500/10',
    },
    reconnecting: {
      icon: Loader2,
      label: 'Reconnecting',
      className: 'text-yellow-500 border-yellow-500/30 bg-yellow-500/10',
    },
    offline: {
      icon: WifiOff,
      label: 'Offline',
      className: 'text-red-500 border-red-500/30 bg-red-500/10',
    },
  }
  const { icon: Icon, label, className } = config[state]

  return (
    <Badge
      variant="outline"
      className={cn('gap-1.5 text-xs font-normal', className)}
      role="status"
      aria-label={`Connection status: ${label}`}
    >
      <Icon
        className={cn('h-3 w-3', state === 'reconnecting' && 'animate-spin')}
        aria-hidden="true"
      />
      <span className="hidden lg:inline">{label}</span>
    </Badge>
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
}: AppTopbarProps) {
  return (
    <header
      data-testid="app-topbar"
      className="sticky top-0 z-20 flex h-18 items-center gap-2 border-b border-slate-100 bg-white px-4 shadow-sm"
    >
      {/* Left cluster */}
      <div className="flex items-center gap-2">
        {showMenuButton && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onMenuClick}
            aria-label="Open menu"
            className="md:hidden h-9 w-9"
          >
            <Menu className="h-5 w-5" />
          </Button>
        )}
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 bg-indigo-50 rounded-lg flex items-center justify-center text-indigo-500">
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 5v14l11 -7z" />
            </svg>
          </div>
          <span className="text-lg font-bold text-slate-900 tracking-tight">Online Trader</span>
        </div>
      </div>

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-1">
        <TooltipProvider delayDuration={300}>
          <ConnectionPill state={connectionState} />

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
                <Bell className="h-4 w-4" />
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
                <HelpCircle className="h-4 w-4" />
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
                <Terminal className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Command Palette <kbd className="ml-1 rounded bg-slate-100 px-1 text-[10px]">⌘K</kbd>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* User menu */}
        {userEmail && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="ml-1 gap-2 text-xs text-slate-600">
                <span className="hidden lg:inline max-w-[120px] truncate">{userEmail}</span>
                <span className="h-6 w-6 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium text-primary">
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
