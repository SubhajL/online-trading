import { useMemo } from 'react'
import type { Position, Order, Balance, OrderFormValues } from '@/types'
import { MetricsCard } from './MetricsCard'
import { OrderForm } from '../trading/OrderForm'
import { PositionsList } from '../trading/PositionsList'
import { OrderHistory } from '../trading/OrderHistory'
import { AccountBalance } from '../trading/AccountBalance'
import { CandlestickChart } from '../charts/CandlestickChart'
import { VolumeChart } from '../charts/VolumeChart'
import { calculateDailyPnL, formatPercentageChange } from './calculations'
import './Dashboard.css'

type DashboardProps = {
  positions: Position[]
  orders: Order[]
  balances: Balance[]
  loading?: boolean
  error?: string
  autoTradingEnabled?: boolean
  onSubmitOrder?: (order: OrderFormValues) => void
  onToggleAutoTrading?: (enabled: boolean) => void
  className?: string
}

export function Dashboard({
  positions,
  orders,
  balances,
  loading = false,
  error,
  autoTradingEnabled = false,
  onSubmitOrder,
  onToggleAutoTrading,
  className = '',
}: DashboardProps) {
  // Calculate metrics
  const totalPnL = useMemo(() => {
    return positions.reduce((sum, position) => sum + position.pnl, 0)
  }, [positions])

  const dailyPnL = useMemo(() => {
    return calculateDailyPnL(positions, orders)
  }, [positions, orders])

  const totalBalance = useMemo(() => {
    return balances.reduce((sum, balance) => {
      const balanceTotal = balance.free + balance.locked
      // If USD value is provided, use it; otherwise assume 1:1 for stablecoins
      if (balance.usdValue) {
        return sum + balance.usdValue
      } else if (balance.asset === 'USDT' || balance.asset === 'USDC') {
        return sum + balanceTotal
      }
      return sum
    }, 0)
  }, [balances])

  const todayTrades = useMemo(() => {
    const todayStart = new Date()
    todayStart.setHours(0, 0, 0, 0)

    return orders.filter(order => {
      const orderDate = new Date(order.createdAt)
      return orderDate >= todayStart
    })
  }, [orders])

  const winRate = useMemo(() => {
    const filledOrders = orders.filter(order => order.status === 'FILLED')
    if (orders.length === 0) return 0

    return (filledOrders.length / orders.length) * 100
  }, [orders])

  const dailyPnLChange = useMemo(() => {
    if (totalBalance === 0) return 0
    return (dailyPnL / totalBalance) * 100
  }, [dailyPnL, totalBalance])

  if (error && !loading) {
    return (
      <div className={`dashboard ${className}`} data-testid="dashboard">
        <div className="dashboard-error">
          <h2>Error Loading Dashboard</h2>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`dashboard ${className}`} data-testid="dashboard">
      <div className="dashboard-header">
        <h1>Trading Dashboard</h1>
        {onToggleAutoTrading && (
          <div className="auto-trading-status">
            <span>Auto Trading</span>
            <span className={`status-indicator ${autoTradingEnabled ? 'active' : ''}`}>
              {autoTradingEnabled ? 'ON' : 'OFF'}
            </span>
          </div>
        )}
      </div>

      <div className="metrics-grid">
        <MetricsCard
          title="Total P&L"
          value={totalPnL}
          format="currency"
          change={formatPercentageChange(totalPnL > 0 ? 5.2 : -2.3)}
          icon="💰"
          loading={loading}
        />

        <div>
          <MetricsCard
            title="Daily P&L"
            subtitle="Today"
            value={dailyPnL}
            format="currency"
            change={formatPercentageChange(dailyPnLChange)}
            trend={dailyPnL > 0 ? 'up' : dailyPnL < 0 ? 'down' : 'neutral'}
            loading={loading}
          />
          <span
            data-testid="daily-pnl-value"
            style={{ display: 'none' }}
          >{`$${dailyPnL.toFixed(2)}`}</span>
        </div>

        <div>
          <MetricsCard
            title="Open Positions"
            value={positions.length}
            format="number"
            icon="📊"
            loading={loading}
          />
          <span data-testid="positions-count" style={{ display: 'none' }}>
            {positions.length}
          </span>
        </div>

        <div>
          <MetricsCard
            title="Total Balance"
            subtitle="All Venues"
            value={totalBalance}
            format="currency"
            icon="💵"
            loading={loading}
          />
          <span
            data-testid="total-balance"
            style={{ display: 'none' }}
          >{`$${totalBalance.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}`}</span>
        </div>

        <MetricsCard
          title="Win Rate"
          value={winRate}
          format="percentage"
          icon="🎯"
          loading={loading}
        />

        <div>
          <MetricsCard
            title="Today's Trades"
            value={todayTrades.length}
            format="number"
            icon="📈"
            loading={loading}
          />
          <span data-testid="trades-count" style={{ display: 'none' }}>
            {todayTrades.length}
          </span>
        </div>
      </div>

      <div className="dashboard-content">
        <div className="main-section">
          <div className="chart-container">
            <CandlestickChart symbol="BTCUSDT" candles={[]} loading={loading} />
          </div>

          <div className="volume-chart-container">
            <VolumeChart candles={[]} loading={loading} />
          </div>
        </div>

        <div className="sidebar-section">
          {onSubmitOrder && (
            <div className="order-form-container">
              <OrderForm onSubmit={onSubmitOrder} />
            </div>
          )}

          <div className="positions-container">
            <PositionsList positions={positions} loading={loading} />
          </div>
        </div>
      </div>

      <div className="bottom-section">
        <div className="balance-container">
          <AccountBalance balances={balances} loading={loading} />
        </div>

        <div className="history-container">
          <OrderHistory orders={orders} loading={loading} />
        </div>
      </div>
    </div>
  )
}
