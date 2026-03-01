import { cn } from '@/lib/utils'

type MaterialIconProps = {
  name: string
  className?: string
  ariaLabel?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

const SIZE_CLASSES = {
  sm: 'text-[16px]',
  md: 'text-[20px]',
  lg: 'text-[24px]',
  xl: 'text-[32px]',
} as const

/**
 * Material Symbols Outlined icon component.
 * Renders icons using the Material Symbols font loaded in layout.tsx.
 *
 * @param name - Material Symbol icon name (e.g., "notifications", "search", "settings")
 * @param className - Additional CSS classes
 * @param ariaLabel - Accessible label for non-decorative icons
 * @param size - Icon size preset: sm (16px), md (20px), lg (24px), xl (32px)
 */
export function MaterialIcon({ name, className, ariaLabel, size = 'lg' }: MaterialIconProps) {
  const isDecorative = !ariaLabel

  return (
    <span
      className={cn(
        'material-symbols-outlined',
        'leading-none select-none',
        SIZE_CLASSES[size],
        className,
      )}
      data-testid={`icon-${name}`}
      aria-hidden={isDecorative ? 'true' : undefined}
      aria-label={ariaLabel}
      role={isDecorative ? undefined : 'img'}
    >
      {name}
    </span>
  )
}
