'use client'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import type { Alert, AlertPriority, AlertType } from '@/types/alerts'

type AlertsDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  alerts: Alert[]
  onMarkAllRead?: () => void
}

type AlertTone = 'info' | 'warning' | 'error'

const priorityToTone: Record<AlertPriority, AlertTone> = {
  low: 'info',
  medium: 'warning',
  high: 'error',
  critical: 'error',
}

function resolveTone(alert: Alert): AlertTone {
  if (alert.type === 'error') return 'error'
  if (alert.type === 'info') return 'info'
  return priorityToTone[alert.priority]
}

const toneConfig: Record<
  AlertTone,
  {
    icon: string
    iconClassName: string
    borderClassName: string
    bgClassName: string
    badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline'
  }
> = {
  info: {
    icon: 'info',
    iconClassName: 'text-blue-400',
    borderClassName: 'border-l-blue-500/60',
    bgClassName: 'bg-blue-500/10',
    badgeVariant: 'outline',
  },
  warning: {
    icon: 'warning',
    iconClassName: 'text-yellow-400',
    borderClassName: 'border-l-yellow-500/60',
    bgClassName: 'bg-yellow-500/10',
    badgeVariant: 'secondary',
  },
  error: {
    icon: 'cancel',
    iconClassName: 'text-red-400',
    borderClassName: 'border-l-red-500/60',
    bgClassName: 'bg-red-500/10',
    badgeVariant: 'destructive',
  },
}

function formatRelativeTime(date: Date): string {
  const now = Date.now()
  const diffMs = now - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)

  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

function formatAlertType(type: AlertType): string {
  switch (type) {
    case 'smc':
      return 'SMC'
    case 'decision':
      return 'Decision'
    case 'position':
      return 'Position'
    case 'order':
      return 'Order'
    case 'error':
      return 'Error'
    case 'info':
      return 'Info'
    default:
      return type
  }
}

export function AlertsDrawer({ open, onOpenChange, alerts, onMarkAllRead }: AlertsDrawerProps) {
  const unreadCount = alerts.filter(a => !a.read).length

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex flex-col gap-0 p-0">
        <SheetHeader className="border-b border-border px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <SheetTitle className="text-base">Alerts</SheetTitle>
              {unreadCount > 0 && (
                <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-[10px]">
                  {unreadCount}
                </Badge>
              )}
            </div>
            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onMarkAllRead}
                className="text-xs text-slate-400"
              >
                Mark all as read
              </Button>
            )}
          </div>
          <SheetDescription className="sr-only">System alerts and notifications</SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1">
          {alerts.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center gap-3 py-16 text-slate-400"
              data-testid="alerts-empty-state"
            >
              <MaterialIcon name="notifications" size="xl" className="opacity-40" />
              <p className="text-sm">No alerts</p>
            </div>
          ) : (
            <ul className="p-3 space-y-2" role="list" aria-label="Alerts list">
              {alerts.map(alert => {
                const tone = resolveTone(alert)
                const { icon, iconClassName, borderClassName, bgClassName, badgeVariant } =
                  toneConfig[tone]
                const createdAt = new Date(alert.createdAt)
                return (
                  <li
                    key={alert.id}
                    className={cn(
                      'flex gap-3 rounded-md border border-border px-4 py-3',
                      'border-l-2',
                      borderClassName,
                      bgClassName,
                      !alert.read && 'ring-1 ring-primary/30',
                    )}
                  >
                    <MaterialIcon name={icon} size="md" className={cn('mt-0.5', iconClassName)} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-900">{alert.title}</p>
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <Badge variant={badgeVariant} className="h-5 px-2 text-[10px]">
                              {alert.priority.toUpperCase()}
                            </Badge>
                            <span className="text-xs text-slate-400">
                              {formatAlertType(alert.type)}
                            </span>
                          </div>
                        </div>
                        <time className="shrink-0 text-xs text-slate-400">
                          {Number.isNaN(createdAt.getTime()) ? '' : formatRelativeTime(createdAt)}
                        </time>
                      </div>
                      <p className="mt-2 text-xs text-slate-600">{alert.message}</p>
                    </div>
                    {!alert.read && (
                      <span
                        className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary"
                        aria-label="Unread"
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

export type { AlertsDrawerProps }
