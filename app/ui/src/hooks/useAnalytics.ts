import { useMemo } from 'react'
import { useOrderHistory } from './useOrderHistory'
import { usePositions } from './usePositions'
import type { Order } from '@/types'

type TimeFrame = '24h' | '7d' | '30d' | '90d' | '1y' | 'all'

type AnalyticsData = {
  performance: {
    totalReturn: number
    winRate: number
    profitFactor: number
    sharpeRatio: number
    maxDrawdown: number
    avgWin: number
    avgLoss: number
    bestTrade: number
    worstTrade: number
  }
  tradingStats: {
    totalTrades: number
    winningTrades: number
    losingTrades: number
    avgHoldTime: string
    totalVolume: number
    totalCommission: number
  }
  symbols: Array<{
    symbol: string
    trades: number
    pnl: number
    winRate: number
  }>
  weeklyPnL: Array<{
    week: string
    pnl: number
  }>
}

type UseAnalyticsReturn = {
  data: AnalyticsData
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function getDateRangeFromTimeframe(timeframe: TimeFrame): string {
  switch (timeframe) {
    case '24h':
      return '1d'
    case '7d':
      return '7d'
    case '30d':
      return '30d'
    case '90d':
      return '90d'
    case '1y':
    case 'all':
      return 'all'
    default:
      return 'all'
  }
}

function calculatePnL(order: Order): number {
  if (order.status !== 'FILLED' || !order.executedQuantity) return 0

  const price = order.avgPrice || order.price || 0
  const quantity = order.executedQuantity
  const fee = order.fee || 0

  // Simple P&L calculation - in reality would need entry/exit pairs
  // For demo, assume BUY orders are negative (cost) and SELL orders are positive (revenue)
  const grossPnL = order.side === 'SELL' ? price * quantity : -(price * quantity)
  return grossPnL - fee
}

export function useAnalytics(timeframe: TimeFrame = '7d'): UseAnalyticsReturn {
  const _dateRange = getDateRangeFromTimeframe(timeframe)
  void _dateRange // Date range is used for future filtering

  const {
    orders,
    loading: ordersLoading,
    error: ordersError,
    refresh: refreshOrders,
  } = useOrderHistory({ status: 'FILLED' }, undefined)

  const {
    totalPnl: openPositionsPnL,
    loading: positionsLoading,
    error: positionsError,
    refresh: refreshPositions,
  } = usePositions()

  const { filteredOrders, stats, ordersBySymbol } = useMemo(() => {
    // Filter orders by timeframe
    const now = new Date()
    const cutoffDate = new Date()

    switch (timeframe) {
      case '24h':
        cutoffDate.setDate(now.getDate() - 1)
        break
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '30d':
        cutoffDate.setDate(now.getDate() - 30)
        break
      case '90d':
        cutoffDate.setDate(now.getDate() - 90)
        break
      case '1y':
        cutoffDate.setFullYear(now.getFullYear() - 1)
        break
      case 'all':
        cutoffDate.setTime(0) // Beginning of time
        break
    }

    const filtered = orders.filter(order => new Date(order.createdAt) >= cutoffDate)

    // Calculate P&L for each order
    const ordersWithPnL = filtered.map(order => ({
      ...order,
      pnl: calculatePnL(order),
    }))

    // Calculate stats
    const winningOrders = ordersWithPnL.filter(o => o.pnl > 0)
    const losingOrders = ordersWithPnL.filter(o => o.pnl < 0)

    const totalVolume = ordersWithPnL.reduce((sum, order) => {
      const price = order.avgPrice || order.price || 0
      const quantity = order.executedQuantity || 0
      return sum + price * quantity
    }, 0)

    const totalCommission = ordersWithPnL.reduce((sum, order) => sum + (order.fee || 0), 0)

    // Group by symbol
    const bySymbol = ordersWithPnL.reduce(
      (acc, order) => {
        const symbol = order.symbol.toString()
        if (!acc[symbol]) {
          acc[symbol] = []
        }
        acc[symbol].push(order)
        return acc
      },
      {} as Record<string, typeof ordersWithPnL>,
    )

    return {
      filteredOrders: ordersWithPnL,
      stats: {
        totalTrades: filtered.length,
        winningTrades: winningOrders.length,
        losingTrades: losingOrders.length,
        totalVolume,
        totalCommission,
      },
      ordersBySymbol: bySymbol,
    }
  }, [orders, timeframe])

  const analyticsData = useMemo<AnalyticsData>(() => {
    // Calculate performance metrics
    const totalPnL = filteredOrders.reduce((sum, order) => sum + order.pnl, 0) + openPositionsPnL
    const wins = filteredOrders.filter(o => o.pnl > 0)
    const losses = filteredOrders.filter(o => o.pnl < 0)

    const avgWin = wins.length > 0 ? wins.reduce((sum, o) => sum + o.pnl, 0) / wins.length : 0
    const avgLoss =
      losses.length > 0 ? Math.abs(losses.reduce((sum, o) => sum + o.pnl, 0) / losses.length) : 0
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? 999 : 0

    const sortedByPnL = [...filteredOrders].sort((a, b) => b.pnl - a.pnl)
    const bestTrade = sortedByPnL[0]?.pnl || 0
    const worstTrade = sortedByPnL[sortedByPnL.length - 1]?.pnl || 0

    // Calculate symbol performance
    const symbolStats = Object.entries(ordersBySymbol)
      .map(([symbol, orders]) => {
        const symbolWins = orders.filter(o => o.pnl > 0)
        const symbolPnL = orders.reduce((sum, o) => sum + o.pnl, 0)
        const winRate = orders.length > 0 ? (symbolWins.length / orders.length) * 100 : 0

        return {
          symbol,
          trades: orders.length,
          pnl: symbolPnL,
          winRate,
        }
      })
      .sort((a, b) => b.pnl - a.pnl)
      .slice(0, 5)

    // Calculate weekly P&L (simplified - last 4 weeks)
    const weeklyPnL = []
    for (let i = 0; i < 4; i++) {
      const weekStart = new Date()
      weekStart.setDate(weekStart.getDate() - (i + 1) * 7)
      const weekEnd = new Date()
      weekEnd.setDate(weekEnd.getDate() - i * 7)

      const weekOrders = filteredOrders.filter(o => {
        const orderDate = new Date(o.createdAt)
        return orderDate >= weekStart && orderDate < weekEnd
      })

      const weekPnL = weekOrders.reduce((sum, o) => sum + o.pnl, 0)
      weeklyPnL.unshift({
        week: `Week ${4 - i}`,
        pnl: weekPnL,
      })
    }

    return {
      performance: {
        totalReturn: stats.totalVolume > 0 ? (totalPnL / stats.totalVolume) * 100 : 0,
        winRate: stats.totalTrades > 0 ? (stats.winningTrades / stats.totalTrades) * 100 : 0,
        profitFactor,
        sharpeRatio: 0, // Would need returns time series
        maxDrawdown: 0, // Would need equity curve
        avgWin,
        avgLoss,
        bestTrade,
        worstTrade,
      },
      tradingStats: {
        ...stats,
        avgHoldTime: '0h 0m', // Would need entry/exit timestamps
      },
      symbols: symbolStats,
      weeklyPnL,
    }
  }, [filteredOrders, stats, ordersBySymbol, openPositionsPnL])

  return {
    data: analyticsData,
    loading: ordersLoading || positionsLoading,
    error: ordersError || positionsError,
    refresh: async () => {
      await Promise.all([refreshOrders(), refreshPositions()])
    },
  }
}
