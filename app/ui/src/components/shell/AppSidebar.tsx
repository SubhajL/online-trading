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
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/trades', label: 'Trades', icon: TrendingUp },
  { path: '/portfolio', label: 'Portfolio', icon: Briefcase },
  { path: '/history', label: 'History', icon: History },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: Settings },
] as const

type ConnectionState = 'connected' | 'reconnecting' | 'offline'

type AppSidebarProps = {
  isOpen: boolean
  onToggle: () => void
  connectionState?: ConnectionState
}

function ConnectionIndicator({ state, compact }: { state: ConnectionState; compact: boolean }) {
  const config = {
    connected: { color: 'bg-green-500', label: 'Connected' },
    reconnecting: { color: 'bg-yellow-500 animate-pulse', label: 'Reconnecting' },
    offline: { color: 'bg-red-500', label: 'Offline' },
  }
  const { color, label } = config[state]

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <span
        className={cn('h-2 w-2 rounded-full shrink-0', color)}
        role="status"
        aria-label={label}
      />
      {!compact && <span className="text-xs text-slate-400">{label}</span>}
    </div>
  )
}

function SidebarNav({ compact, onNavigate }: { compact: boolean; onNavigate?: () => void }) {
  const pathname = usePathname()

  return (
    <TooltipProvider delayDuration={0}>
      <nav className="flex flex-col gap-1 px-2 py-2" aria-label="Main navigation">
        {NAV_ITEMS.map(item => {
          const Icon = item.icon
          const active = isPathActive(pathname, item.path)

          const link = (
            <Link
              key={item.path}
              href={item.path}
              onClick={onNavigate}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150',
                'min-h-touch hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus',
                active
                  ? 'bg-indigo-50 text-indigo-600 border-l-2 border-indigo-500'
                  : 'text-slate-500 hover:text-slate-700',
                compact && 'justify-center px-2',
              )}
            >
              <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
              {!compact && <span>{item.label}</span>}
            </Link>
          )

          if (compact) {
            return (
              <Tooltip key={item.path}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  {item.label}
                </TooltipContent>
              </Tooltip>
            )
          }

          return link
        })}
      </nav>
    </TooltipProvider>
  )
}

export function AppSidebar({ isOpen, onToggle, connectionState = 'connected' }: AppSidebarProps) {
  return (
    <>
      {/* Desktop sidebar */}
      <aside
        data-testid="app-sidebar"
        className={cn(
          'hidden md:flex flex-col border-r border-slate-100 bg-white shadow-[1px_0_8px_rgba(0,0,0,0.03)] transition-all duration-normal',
          'h-[calc(100vh-3.5rem)] sticky top-14',
          isOpen ? 'w-[220px]' : 'w-[60px]',
        )}
      >
        <div className="flex items-center justify-end p-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            className="h-8 w-8"
          >
            {isOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>

        <SidebarNav compact={!isOpen} />

        <div className="mt-auto">
          <Separator />
          <ConnectionIndicator state={connectionState} compact={!isOpen} />
          {isOpen && <div className="px-3 pb-2 text-xs text-slate-300">v1.0.0</div>}
        </div>
      </aside>
    </>
  )
}

export function MobileSidebar({
  connectionState = 'connected',
  open,
  onOpenChange,
}: {
  connectionState?: ConnectionState
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[260px] bg-[#FAFBFC] p-0">
        <div className="flex flex-col h-full pt-4">
          <SidebarNav compact={false} />
          <div className="mt-auto">
            <Separator />
            <ConnectionIndicator state={connectionState} compact={false} />
            <div className="px-3 pb-4 text-xs text-slate-300">v1.0.0</div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
