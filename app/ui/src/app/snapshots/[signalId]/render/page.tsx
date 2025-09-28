'use client'

import { useEffect, useState, useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import { Chart } from '@/components/charts/Chart'
import { marketDataService } from '@/services/market-data'
import type { Candle, Timeframe } from '@/types'

// Declare global for Puppeteer to detect readiness
declare global {
  interface Window {
    __SNAPSHOT_READY__?: boolean
  }
}

export default function SnapshotRenderPage() {
  const searchParams = useSearchParams()
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)

  // Parse query parameters
  const symbol = searchParams.get('symbol') || 'BTCUSDT'
  const timeframe = searchParams.get('timeframe') || '15m'
  const side = searchParams.get('side') as 'BUY' | 'SELL'
  const entry = parseFloat(searchParams.get('entry') || '0')
  const stopLoss = parseFloat(searchParams.get('stopLoss') || '0')
  const takeProfit = parseFloat(searchParams.get('takeProfit') || '0')
  const signalTime = searchParams.get('signalTime') || new Date().toISOString()
  const preCandles = parseInt(searchParams.get('preCandles') || '100')
  const postCandles = parseInt(searchParams.get('postCandles') || '20')
  const reasonsParam = searchParams.get('reasons') || ''
  const reasons = reasonsParam ? reasonsParam.split(',') : []

  // Calculate time window for candle fetch
  const { startTime, endTime } = useMemo(() => {
    const signalDate = new Date(signalTime)
    const candleDurationMs =
      {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
      }[timeframe] || 15 * 60 * 1000

    const start = new Date(signalDate.getTime() - preCandles * candleDurationMs)
    const end = new Date(signalDate.getTime() + postCandles * candleDurationMs)

    return {
      startTime: start.toISOString(),
      endTime: end.toISOString(),
    }
  }, [signalTime, timeframe, preCandles, postCandles])

  // Fetch candles
  useEffect(() => {
    async function fetchCandles() {
      try {
        const data = await marketDataService.getHistoricalCandles(
          symbol,
          timeframe,
          new Date(startTime),
          new Date(endTime),
        )
        setCandles(data)
      } catch (error) {
        console.error('Failed to fetch candles:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchCandles()
  }, [symbol, timeframe, startTime, endTime])

  // Signal chart readiness
  useEffect(() => {
    if (!loading && candles.length > 0) {
      // Wait for next frame to ensure chart is painted
      requestAnimationFrame(() => {
        window.__SNAPSHOT_READY__ = true
      })
    }
  }, [loading, candles])

  // Create marker for signal
  const signalMarker = useMemo(() => {
    const signalTimestamp = Math.floor(new Date(signalTime).getTime() / 1000)
    return {
      time: signalTimestamp,
      type: side,
    }
  }, [signalTime, side])

  // Fixed layout for consistent snapshots
  const containerStyle = {
    width: '1200px',
    height: '628px',
    backgroundColor: '#0a0a0a',
    position: 'relative' as const,
    fontFamily: 'system-ui, -apple-system, sans-serif',
  }

  const chartWrapperStyle = {
    width: '100%',
    height: '100%',
    position: 'relative' as const,
  }

  const overlayStyle = {
    position: 'absolute' as const,
    top: '16px',
    left: '16px',
    display: 'flex',
    gap: '8px',
    flexWrap: 'wrap' as const,
    maxWidth: '400px',
    pointerEvents: 'none' as const,
  }

  const reasonBadgeStyle = {
    background: 'rgba(59, 130, 246, 0.2)',
    border: '1px solid rgba(59, 130, 246, 0.5)',
    color: '#60a5fa',
    padding: '4px 12px',
    borderRadius: '16px',
    fontSize: '12px',
    fontWeight: '500',
  }

  const signalInfoStyle = {
    position: 'absolute' as const,
    bottom: '16px',
    right: '16px',
    background: 'rgba(0, 0, 0, 0.8)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '8px',
    padding: '12px 16px',
    fontSize: '12px',
    color: '#e5e7eb',
    pointerEvents: 'none' as const,
  }

  if (loading) {
    return (
      <div style={containerStyle}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
          }}
        >
          <div style={{ color: '#6b7280' }}>Loading chart data...</div>
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={chartWrapperStyle}>
        <Chart
          symbol={symbol}
          timeframe={timeframe as Timeframe}
          markers={[signalMarker]}
          levels={{ entry, stopLoss, takeProfit }}
          showSmcOverlays
          showZoneOverlays
          onReady={() => {
            window.__SNAPSHOT_READY__ = true
          }}
        />
      </div>

      {/* Reason badges */}
      {reasons.length > 0 && (
        <div style={overlayStyle}>
          {reasons.map((reason, i) => (
            <div key={i} style={reasonBadgeStyle}>
              {reason}
            </div>
          ))}
        </div>
      )}

      {/* Signal info */}
      <div style={signalInfoStyle}>
        <div
          style={{
            marginBottom: '4px',
            fontWeight: '600',
            color: side === 'BUY' ? '#10b981' : '#ef4444',
          }}
        >
          {side} {symbol}
        </div>
        <div style={{ opacity: 0.8 }}>
          Entry: {entry} | SL: {stopLoss} | TP: {takeProfit}
        </div>
        <div style={{ opacity: 0.6, marginTop: '4px' }}>
          {new Date(signalTime).toLocaleString()} • {timeframe}
        </div>
      </div>
    </div>
  )
}
