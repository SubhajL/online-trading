import { formatCurrency, formatNumber } from '@/utils/formatters'
import './MetricsCard.css'

type MetricsCardProps = {
  title: string
  value: string | number
  change?: string
  subtitle?: string
  loading?: boolean
  error?: string
  icon?: string
  format?: 'currency' | 'percentage' | 'number' | 'none'
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}

export function MetricsCard({
  title,
  value,
  change,
  subtitle,
  loading = false,
  error,
  icon,
  format = 'none',
  trend,
  className = '',
}: MetricsCardProps) {
  const formatValue = (val: string | number): string => {
    if (typeof val === 'string' && format === 'none') {
      return val
    }

    const numValue = typeof val === 'string' ? parseFloat(val) : val

    switch (format) {
      case 'currency':
        return formatCurrency(numValue)
      case 'percentage':
        return `${numValue.toFixed(2)}%`
      case 'number':
        return formatNumber(numValue)
      default:
        return val.toString()
    }
  }

  const getChangeClass = (changeValue: string): string => {
    if (changeValue.startsWith('+')) {
      return 'change-positive'
    } else if (changeValue.startsWith('-')) {
      return 'change-negative'
    }
    return 'change-neutral'
  }

  if (loading) {
    return (
      <div className={`metrics-card ${className}`} data-testid="metrics-card">
        <div className="metrics-header">
          {icon && <span className="metrics-icon">{icon}</span>}
          <div className="metrics-titles">
            <h3 className="metrics-title">{title}</h3>
            {subtitle && <span className="metrics-subtitle">{subtitle}</span>}
          </div>
        </div>
        <div className="metrics-loading" data-testid="metrics-loading">
          <div className="loading-shimmer" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`metrics-card ${className}`} data-testid="metrics-card">
        <div className="metrics-header">
          {icon && <span className="metrics-icon">{icon}</span>}
          <div className="metrics-titles">
            <h3 className="metrics-title">{title}</h3>
            {subtitle && <span className="metrics-subtitle">{subtitle}</span>}
          </div>
        </div>
        <div className="metrics-error" data-testid="metrics-error">
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className={`metrics-card ${className}`} data-testid="metrics-card">
      <div className="metrics-header">
        {icon && <span className="metrics-icon">{icon}</span>}
        <div className="metrics-titles">
          <h3 className="metrics-title">{title}</h3>
          {subtitle && <span className="metrics-subtitle">{subtitle}</span>}
        </div>
      </div>

      <div className="metrics-content">
        <div className="metrics-value">{formatValue(value)}</div>

        <div className="metrics-indicators">
          {change && (
            <span className={`metrics-change ${getChangeClass(change)}`}>
              {change}
            </span>
          )}

          {trend && (
            <span
              className={`trend-indicator trend-${trend}`}
              data-testid="trend-indicator"
            >
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}