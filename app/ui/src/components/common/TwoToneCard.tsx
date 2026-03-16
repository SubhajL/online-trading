import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type TwoToneVariant = 'default' | 'success' | 'warning' | 'danger' | 'info'

type TwoToneCardProps = {
  title: string
  icon?: ReactNode
  actions?: ReactNode
  footer?: ReactNode
  variant?: TwoToneVariant
  children: ReactNode
  className?: string
  bodyClassName?: string
}

const HEADER_VARIANTS: Record<TwoToneVariant, string> = {
  default: 'bg-[#15152a] border-[#323267]',
  success: 'bg-emerald-500/15 border-emerald-500/30',
  warning: 'bg-amber-500/15 border-amber-500/30',
  danger: 'bg-red-500/15 border-red-500/30',
  info: 'bg-sky-500/15 border-sky-500/30',
}

export function TwoToneCard({
  title,
  icon,
  actions,
  footer,
  variant = 'default',
  children,
  className,
  bodyClassName,
}: TwoToneCardProps) {
  return (
    <section
      className={cn(
        'overflow-hidden rounded-[18px] border border-[#323267] bg-[#1A1A2E]',
        className,
      )}
    >
      <header
        className={cn(
          'flex items-center justify-between border-b px-4 py-3',
          HEADER_VARIANTS[variant],
        )}
      >
        <div className="flex min-w-0 items-center gap-2">
          {icon}
          <h2 className="truncate text-sm font-semibold uppercase tracking-wide text-slate-200">
            {title}
          </h2>
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </header>
      <div className={cn('p-4', bodyClassName)}>{children}</div>
      {footer && <footer className="border-t border-[#323267] px-4 py-2">{footer}</footer>}
    </section>
  )
}
