const currencySymbols: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CNY: '¥',
}

export function formatCurrency(value: number, currency = 'USD', decimals = 2): string {
  const symbol = currencySymbols[currency] || currency
  const absValue = Math.abs(value)
  const formatted = absValue.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  return value < 0 ? `-${symbol}${formatted}` : `${symbol}${formatted}`
}

export function formatPercentage(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`
}

export function formatNumber(value: number, decimals?: number): string {
  const options: Intl.NumberFormatOptions = {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }

  if (decimals === undefined) {
    // Preserve original decimal places
    const decimalPlaces = (value.toString().split('.')[1] || '').length
    options.minimumFractionDigits = 0
    options.maximumFractionDigits = decimalPlaces
  }

  return value.toLocaleString('en-US', options)
}
