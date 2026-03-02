import { cn } from '@/lib/utils'

type BusBarProps = {
  nodes: string[]
  activeCount?: number
  className?: string
}

export function BusBar({ nodes, activeCount = nodes.length, className }: BusBarProps) {
  const safeActiveCount = Math.max(0, Math.min(activeCount, nodes.length))

  return (
    <div className={cn('relative flex items-center justify-between gap-2', className)}>
      <div className="absolute left-0 right-0 top-4 h-[3px] rounded bg-[#323267]" />
      {nodes.map((node, index) => {
        const active = index < safeActiveCount
        return (
          <div key={node} className="z-[1] flex flex-col items-center gap-1">
            <span
              className={cn(
                'h-3.5 w-3.5 rounded-full border-2 bg-[#101022]',
                active
                  ? 'border-primary shadow-[0_0_8px_rgba(99,99,242,0.8)]'
                  : 'border-slate-500/70',
              )}
            />
            <span
              className={cn(
                'text-[10px] font-mono uppercase tracking-wide',
                active ? 'text-slate-300' : 'text-slate-500',
              )}
            >
              {node}
            </span>
          </div>
        )
      })}
    </div>
  )
}
