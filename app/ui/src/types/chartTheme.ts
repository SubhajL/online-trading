/**
 * Lightweight Charts theme configuration
 * Maps to chart library theme API
 */
export interface ChartTheme {
  layout: {
    background: { color: string }
    textColor: string
  }
  grid: {
    vertLines: { color: string }
    horzLines: { color: string }
  }
  timeScale: {
    borderColor: string
  }
  rightPriceScale: {
    borderColor: string
  }
}
