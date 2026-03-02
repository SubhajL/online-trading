import { cn } from '@/lib/utils'
import { MaterialIcon } from './MaterialIcon'

type IntegrationPillProps = {
  transport: 'REST' | 'WS'
  endpoint: string
  className?: string
}

export function IntegrationPill({ transport, endpoint, className }: IntegrationPillProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-slate-600/60 bg-[#15152a] px-2.5 py-1 text-[10px] font-mono text-slate-400',
        className,
      )}
      aria-label={`${transport}: ${endpoint}`}
    >
      <MaterialIcon name="terminal" size="sm" className="text-slate-500" />
      <span>{transport}:</span>
      <span>{endpoint}</span>
    </span>
  )
}
