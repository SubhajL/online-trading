import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ChartToolbar } from './ChartToolbar'
import type { TimeFrame, ChartType, IndicatorType } from '@/types'

describe('ChartToolbar', () => {
  const mockProps = {
    timeframe: '1m' as TimeFrame,
    chartType: 'candlestick' as ChartType,
    indicators: ['EMA', 'RSI'] as IndicatorType[],
    onTimeframeChange: vi.fn(),
    onChartTypeChange: vi.fn(),
    onIndicatorToggle: vi.fn(),
  }

  it('renders toolbar container', () => {
    render(<ChartToolbar {...mockProps} />)

    const toolbar = screen.getByTestId('chart-toolbar')
    expect(toolbar).toBeInTheDocument()
    expect(toolbar).toHaveClass('chart-toolbar')
  })

  it('renders timeframe selector', () => {
    render(<ChartToolbar {...mockProps} />)

    expect(screen.getByText('1m')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /timeframe/i })).toBeInTheDocument()
  })

  it('renders chart type selector', () => {
    render(<ChartToolbar {...mockProps} />)

    expect(screen.getByText('Candlestick')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /chart type/i })).toBeInTheDocument()
  })

  it('renders indicator toggles', () => {
    render(<ChartToolbar {...mockProps} />)

    expect(screen.getByText('EMA')).toBeInTheDocument()
    expect(screen.getByText('RSI')).toBeInTheDocument()
    // Should show all 5 available indicators
    expect(screen.getAllByRole('checkbox')).toHaveLength(5)
  })

  it('calls onTimeframeChange when timeframe is selected', async () => {
    const user = userEvent.setup()
    render(<ChartToolbar {...mockProps} />)

    const timeframeButton = screen.getByRole('button', { name: /timeframe/i })
    await user.click(timeframeButton)

    const fiveMinOption = screen.getByText('5m')
    await user.click(fiveMinOption)

    expect(mockProps.onTimeframeChange).toHaveBeenCalledWith('5m')
  })

  it('calls onChartTypeChange when chart type is selected', async () => {
    const user = userEvent.setup()
    render(<ChartToolbar {...mockProps} />)

    const chartTypeButton = screen.getByRole('button', { name: /chart type/i })
    await user.click(chartTypeButton)

    const lineOption = screen.getByText('Line')
    await user.click(lineOption)

    expect(mockProps.onChartTypeChange).toHaveBeenCalledWith('line')
  })

  it('calls onIndicatorToggle when indicator is toggled', async () => {
    const user = userEvent.setup()
    render(<ChartToolbar {...mockProps} />)

    const emaCheckbox = screen.getByRole('checkbox', { name: /EMA/i })
    await user.click(emaCheckbox)

    expect(mockProps.onIndicatorToggle).toHaveBeenCalledWith('EMA')
  })

  it('shows all available timeframes', async () => {
    const user = userEvent.setup()
    render(<ChartToolbar {...mockProps} />)

    const timeframeButton = screen.getByRole('button', { name: /timeframe/i })
    await user.click(timeframeButton)

    const timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
    timeframes.forEach(tf => {
      const elements = screen.getAllByText(tf)
      expect(elements.length).toBeGreaterThan(0)
    })
  })

  it('shows all chart types', async () => {
    const user = userEvent.setup()
    render(<ChartToolbar {...mockProps} />)

    const chartTypeButton = screen.getByRole('button', { name: /chart type/i })
    await user.click(chartTypeButton)

    const chartTypes = ['Candlestick', 'Line', 'Area']
    chartTypes.forEach(type => {
      const elements = screen.getAllByText(type)
      expect(elements.length).toBeGreaterThan(0)
    })
  })

  it('shows all available indicators', () => {
    const allIndicators = ['EMA', 'SMA', 'RSI', 'MACD', 'BB'] as IndicatorType[]
    render(<ChartToolbar {...mockProps} indicators={allIndicators} />)

    allIndicators.forEach(indicator => {
      expect(screen.getByText(indicator)).toBeInTheDocument()
    })
  })

  it('applies custom className', () => {
    render(<ChartToolbar {...mockProps} className="custom-toolbar" />)

    const toolbar = screen.getByTestId('chart-toolbar')
    expect(toolbar).toHaveClass('chart-toolbar', 'custom-toolbar')
  })

  it('disables controls when disabled prop is true', () => {
    render(<ChartToolbar {...mockProps} disabled />)

    const buttons = screen.getAllByRole('button')
    const checkboxes = screen.getAllByRole('checkbox')

    buttons.forEach(button => {
      expect(button).toBeDisabled()
    })

    checkboxes.forEach(checkbox => {
      expect(checkbox).toBeDisabled()
    })
  })

  it('highlights active timeframe', () => {
    render(<ChartToolbar {...mockProps} timeframe="15m" />)

    const activeButton = screen.getByRole('button', { name: /timeframe/i })
    expect(activeButton).toHaveTextContent('15m')
  })

  it('shows correct chart type label', () => {
    render(<ChartToolbar {...mockProps} chartType="line" />)

    const chartTypeButton = screen.getByRole('button', { name: /chart type/i })
    expect(chartTypeButton).toHaveTextContent('Line')
  })

  it('checks active indicators', () => {
    render(<ChartToolbar {...mockProps} indicators={['EMA']} />)

    const emaCheckbox = screen.getByRole('checkbox', { name: /EMA/i })
    const rsiCheckbox = screen.getByRole('checkbox', { name: /RSI/i })

    expect(emaCheckbox).toBeChecked()
    expect(rsiCheckbox).not.toBeChecked()
  })
})
