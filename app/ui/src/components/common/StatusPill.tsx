import { cn } from '@/lib/utils'
import { MaterialIcon } from './MaterialIcon'

type StatusPillState = 'connected' | 'reconnecting' | 'offline' | 'active' | 'paused' | 'stopped'

type StatusPillProps = {
  state: StatusPillState
  className?: string
}

const STATUS_CONFIG: Record<
  StatusPillState,
  { label: string; icon: string; className: string; animate?: boolean }
> = {
  connected: {
    label: 'Connected',
    icon: 'wifi',
    className: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  },
  reconnecting: {
    label: 'Reconnecting',
    icon: 'progress_activity',
    className: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
    animate: true,
  },
  offline: {
    label: 'Offline',
    icon: 'wifi_off',
    className: 'text-red-400 border-red-500/30 bg-red-500/10',
  },
  active: {
    label: 'ACTIVE',
    icon: 'play_arrow',
    className: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
  },
  paused: {
    label: 'PAUSED',
    icon: 'pause',
    className: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
  },
  stopped: {
    label: 'STOPPED',
    icon: 'stop',
    className: 'text-red-400 border-red-500/30 bg-red-500/10',
  },
}

export function StatusPill({ state, className }: StatusPillProps) {
  const config = STATUS_CONFIG[state]

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold tracking-wide',
        config.className,
        className,
      )}
      role="status"
      aria-label={config.label}
    >
      <MaterialIcon name={config.icon} size="sm" className={cn(config.animate && 'animate-spin')} />
      <span>{config.label}</span>
    </span>
  )
}
