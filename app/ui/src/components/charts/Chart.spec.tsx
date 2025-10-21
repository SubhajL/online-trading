import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Chart } from './Chart'
import { useChart } from '@/hooks/useChart'
import { useMarketData } from '@/hooks/useMarketData'
import { getTokens } from '@/utils/getTokens'
import { DEFAULT_TOKENS } from '@/constants/defaultTokens'
import type { Candle, Timeframe, SmcEvent, Zone } from '@/types'

vi.mock('@/hooks/useChart')
vi.mock('@/hooks/useMarketData')
vi.mock('@/utils/getTokens', () => ({
  getTokens: vi.fn(),
}))

describe('Chart', () => {
  const mockCandles: Candle[] = [
    { time: 1640995200, open: 45000, high: 45500, low: 44800, close: 45200, volume: 100 },
    { time: 1640995260, open: 45200, high: 45300, low: 45000, close: 45100, volume: 80 },
  ]

  const mockSmcEvents: SmcEvent[] = [
    {
      id: 'smc-1',
      symbol: 'BTCUSDT',
      type: 'CHOCH',
      direction: 'bullish',
      price: 45100,
      timeframe: '15m',
      timestamp: 1640995260,
    },
  ]

  const mockZones: Zone[] = [
    {
      id: 'zone-1',
      symbol: 'BTCUSDT',
      type: 'demand',
      priceFrom: 44800,
      priceTo: 45000,
      strength: 3,
      touches: 1,
      timeframe: '15m',
      created: 1640995200,
    },
  ]

  const mockUseChart = {
    chart: null,
    candlestickSeries: null,
    updateCandles: vi.fn(),
    addIndicator: vi.fn(),
    removeIndicator: vi.fn(),
    fitContent: vi.fn(),
    setChartType: vi.fn(),
    addSmcOverlay: vi.fn(),
    removeSmcOverlay: vi.fn(),
    addZoneOverlay: vi.fn(),
    removeZoneOverlay: vi.fn(),
    addMarkers: vi.fn(),
    addPriceLevels: vi.fn(),
    removePriceLevels: vi.fn(),
    cleanup: vi.fn(),
  }

  const mockUseMarketData = {
    candles: mockCandles,
    indicators: {
      EMA: [
        { time: 1640995200, value: 45100 },
        { time: 1640995260, value: 45150 },
      ],
      RSI: [
        { time: 1640995200, value: 65 },
        { time: 1640995260, value: 62 },
      ],
    },
    smcEvents: mockSmcEvents,
    zones: mockZones,
    loading: false,
    error: null,
    setTimeframe: vi.fn(),
    setSymbol: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useChart).mockReturnValue(mockUseChart)
    vi.mocked(useMarketData).mockReturnValue(mockUseMarketData as any)
    vi.mocked(getTokens).mockReturnValue(DEFAULT_TOKENS)
  })

  describe('rendering', () => {
    it('should render chart container with correct symbol', () => {
      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument()
      expect(screen.getByTestId('chart-container')).toBeInTheDocument()
    })

    it('should show loading spinner when loading', () => {
      vi.mocked(useMarketData).mockReturnValue({
        ...mockUseMarketData,
        loading: true,
      } as any)

      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByTestId('chart-loading')).toBeInTheDocument()
    })

    it('should show error message when error occurs', () => {
      vi.mocked(useMarketData).mockReturnValue({
        ...mockUseMarketData,
        error: 'Failed to load data',
      } as any)

      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByText(/Failed to load data/)).toBeInTheDocument()
    })
  })

  describe('token-based styling', () => {
    it('applies token background to chart container', () => {
      render(<Chart symbol="BTCUSDT" />)

      const container = screen.getByTestId('chart-root')
      expect(container).toHaveStyle({
        backgroundColor: DEFAULT_TOKENS.colors.gray[900],
        borderRadius: DEFAULT_TOKENS.radius.lg,
      })
    })

    it('applies token styles to active timeframe button', () => {
      render(<Chart symbol="BTCUSDT" timeframe="15m" />)

      const button = screen.getByText('15m')
      expect(button).toHaveStyle({
        backgroundColor: DEFAULT_TOKENS.colors.primary[600],
        color: DEFAULT_TOKENS.colors.text.inverse,
      })
    })

    it('applies token styles to chart type select', () => {
      render(<Chart symbol="BTCUSDT" />)

      const select = screen.getByTestId('chart-type-selector')
      expect(select).toHaveStyle({
        backgroundColor: DEFAULT_TOKENS.colors.surface.overlay,
        border: `1px solid ${DEFAULT_TOKENS.colors.border.subtle}`,
        color: DEFAULT_TOKENS.colors.text.primary,
      })
    })

    it('applies token styles to icon buttons', () => {
      render(<Chart symbol="BTCUSDT" />)

      const fitButton = screen.getByTestId('fit-content-button')
      expect(fitButton).toHaveStyle({
        color: DEFAULT_TOKENS.colors.text.muted,
      })
    })

    it('applies token background to loading overlay', () => {
      vi.mocked(useMarketData).mockReturnValue({
        ...mockUseMarketData,
        loading: true,
      } as any)

      render(<Chart symbol="BTCUSDT" />)

      const overlay = screen.getByTestId('chart-loading')
      expect(overlay).toHaveStyle({
        backgroundColor: `${DEFAULT_TOKENS.colors.surface.base}cc`,
      })
    })
  })

  describe('timeframe selection', () => {
    it('should render timeframe buttons', () => {
      render(<Chart symbol="BTCUSDT" />)

      const timeframes: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1d']
      timeframes.forEach(tf => {
        expect(screen.getByText(tf)).toBeInTheDocument()
      })
    })

    it('should handle timeframe change', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const button1h = screen.getByText('1h')
      await user.click(button1h)

      expect(mockUseMarketData.setTimeframe).toHaveBeenCalledWith('1h')
    })

    it('should highlight active timeframe', () => {
      render(<Chart symbol="BTCUSDT" timeframe="15m" />)

      const button15m = screen.getByText('15m')
      expect(button15m.style.backgroundColor).toBeTruthy()
      expect(button15m.style.color).toBeTruthy()
    })
  })

  describe('chart type selection', () => {
    it('should render chart type selector', () => {
      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByTestId('chart-type-selector')).toBeInTheDocument()
    })

    it('should handle chart type change', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const selector = screen.getByTestId('chart-type-selector')
      await user.selectOptions(selector, 'line')

      expect(mockUseChart.setChartType).toHaveBeenCalledWith('line')
    })
  })

  describe('indicator management', () => {
    it('should render indicator panel toggle', () => {
      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByText(/Indicators/)).toBeInTheDocument()
    })

    it('should toggle indicator visibility', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const indicatorToggle = screen.getByTestId('indicator-panel-toggle')
      await user.click(indicatorToggle)

      expect(screen.getByTestId('indicator-panel')).toBeInTheDocument()
    })

    it('should handle indicator toggle', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      // Open indicator panel
      await user.click(screen.getByTestId('indicator-panel-toggle'))

      // Toggle EMA indicator
      const emaToggle = screen.getByLabelText('EMA')
      await user.click(emaToggle)

      expect(mockUseChart.addIndicator).toHaveBeenCalledWith(
        'EMA',
        expect.any(Array),
        expect.any(Object),
      )
    })

    it('should remove indicator when untoggled', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" activeIndicators={['EMA']} />)

      await user.click(screen.getByTestId('indicator-panel-toggle'))
      const emaToggle = screen.getByLabelText('EMA')
      await user.click(emaToggle)

      expect(mockUseChart.removeIndicator).toHaveBeenCalledWith('EMA')
    })
  })

  describe('SMC overlays', () => {
    it('should show SMC overlay toggle', () => {
      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByTestId('smc-overlay-toggle')).toBeInTheDocument()
    })

    it('should toggle SMC overlay visibility', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const smcToggle = screen.getByTestId('smc-overlay-toggle')
      await user.click(smcToggle)

      expect(mockUseChart.addSmcOverlay).toHaveBeenCalledWith(mockSmcEvents)
    })

    it('should update SMC overlays when events change', () => {
      const { rerender } = render(<Chart symbol="BTCUSDT" showSmcOverlays />)

      expect(mockUseChart.addSmcOverlay).toHaveBeenCalledWith(mockSmcEvents)

      const newEvents = [
        ...mockSmcEvents,
        {
          id: 'smc-2',
          symbol: 'BTCUSDT',
          type: 'BOS' as const,
          direction: 'bearish' as const,
          price: 45300,
          timeframe: '15m',
          timestamp: 1640995320,
        },
      ]

      vi.mocked(useMarketData).mockReturnValue({
        ...mockUseMarketData,
        smcEvents: newEvents,
      } as any)

      rerender(<Chart symbol="BTCUSDT" showSmcOverlays />)

      expect(mockUseChart.addSmcOverlay).toHaveBeenCalledWith(newEvents)
    })
  })

  describe('zone overlays', () => {
    it('should show zone overlay toggle', () => {
      render(<Chart symbol="BTCUSDT" />)

      expect(screen.getByTestId('zone-overlay-toggle')).toBeInTheDocument()
    })

    it('should toggle zone overlay visibility', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const zoneToggle = screen.getByTestId('zone-overlay-toggle')
      await user.click(zoneToggle)

      expect(mockUseChart.addZoneOverlay).toHaveBeenCalledWith(mockZones)
    })
  })

  describe('symbol change', () => {
    it('should handle symbol change', () => {
      const { rerender } = render(<Chart symbol="BTCUSDT" />)

      expect(mockUseMarketData.setSymbol).toHaveBeenCalledWith('BTCUSDT')

      rerender(<Chart symbol="ETHUSDT" />)

      expect(mockUseMarketData.setSymbol).toHaveBeenCalledWith('ETHUSDT')
    })
  })

  describe('chart actions', () => {
    it('should fit content on button click', async () => {
      const user = userEvent.setup()
      render(<Chart symbol="BTCUSDT" />)

      const fitButton = screen.getByTestId('fit-content-button')
      await user.click(fitButton)

      expect(mockUseChart.fitContent).toHaveBeenCalled()
    })

    it('should handle fullscreen toggle', async () => {
      const user = userEvent.setup()
      const { container } = render(<Chart symbol="BTCUSDT" />)

      const fullscreenButton = screen.getByTestId('fullscreen-button')
      await user.click(fullscreenButton)

      const chartWrapper = container.firstChild as HTMLElement
      expect(chartWrapper).toHaveStyle({ position: 'fixed' })
      expect(chartWrapper).toHaveStyle({ zIndex: '50' })
    })
  })

  describe('cleanup', () => {
    it('should cleanup chart on unmount', () => {
      const { unmount } = render(<Chart symbol="BTCUSDT" />)

      unmount()

      expect(mockUseChart.cleanup).toHaveBeenCalled()
    })
  })

  describe('token-based styling', () => {
    it('renders container with token-based background', () => {
      const { container } = render(<Chart symbol="BTCUSDT" />)
      const chartWrapper = container.firstChild as HTMLElement
      expect(chartWrapper.style.backgroundColor).toBeTruthy()
      expect(chartWrapper.style.backgroundColor).not.toMatch(/#[0-9a-fA-F]{6}/)
    })

    it('applies active button styles to selected timeframe', () => {
      render(<Chart symbol="BTCUSDT" timeframe="15m" />)
      const button15m = screen.getByRole('button', { name: '15m' })
      expect(button15m.style.backgroundColor).toBeTruthy()
      expect(button15m.style.color).toBeTruthy()
      expect(button15m.style.padding).toBeTruthy()
    })

    it('applies inactive button styles to unselected timeframe', () => {
      render(<Chart symbol="BTCUSDT" timeframe="15m" />)
      const button1m = screen.getByRole('button', { name: '1m' })
      expect(button1m.style.backgroundColor).toBeTruthy()
      expect(button1m.style.color).toBeTruthy()
      expect(button1m.style.padding).toBeTruthy()
    })

    it('applies token styles to indicator toggle button', () => {
      render(<Chart symbol="BTCUSDT" />)
      const indicatorButton = screen.getByTestId('indicator-panel-toggle')
      expect(indicatorButton.style.backgroundColor).toBeTruthy()
      expect(indicatorButton.style.color).toBeTruthy()
      expect(indicatorButton.style.borderRadius).toBeTruthy()
    })

    it('applies inactive token styles to SMC toggle', () => {
      render(<Chart symbol="BTCUSDT" showSmcOverlays={false} />)
      const smcButton = screen.getByTestId('smc-overlay-toggle')
      expect(smcButton.style.backgroundColor).toBeTruthy()
      expect(smcButton.style.color).toBeTruthy()
    })

    it('applies active token styles to SMC toggle', () => {
      render(<Chart symbol="BTCUSDT" showSmcOverlays={true} />)
      const smcButton = screen.getByTestId('smc-overlay-toggle')
      expect(smcButton.style.backgroundColor).toBeTruthy()
      expect(smcButton.style.color).toBeTruthy()
    })

    it('applies inactive token styles to zone toggle', () => {
      render(<Chart symbol="BTCUSDT" showZoneOverlays={false} />)
      const zoneButton = screen.getByTestId('zone-overlay-toggle')
      expect(zoneButton.style.backgroundColor).toBeTruthy()
      expect(zoneButton.style.color).toBeTruthy()
    })

    it('applies active token styles to zone toggle', () => {
      render(<Chart symbol="BTCUSDT" showZoneOverlays={true} />)
      const zoneButton = screen.getByTestId('zone-overlay-toggle')
      expect(zoneButton.style.backgroundColor).toBeTruthy()
      expect(zoneButton.style.color).toBeTruthy()
    })

    it('applies token background to loading overlay', () => {
      vi.mocked(useMarketData).mockReturnValue({
        ...mockUseMarketData,
        loading: true,
      } as any)
      render(<Chart symbol="BTCUSDT" />)
      const loadingOverlay = screen.getByTestId('chart-loading')
      expect(loadingOverlay.style.backgroundColor).toBeTruthy()
    })

    it('does not contain hex color literals', () => {
      const { container } = render(<Chart symbol="BTCUSDT" />)
      const buttons = container.querySelectorAll('button')
      buttons.forEach(button => {
        const bgColor = button.style.backgroundColor
        if (bgColor) {
          expect(bgColor).not.toMatch(/#[0-9a-fA-F]{6}/)
        }
      })
    })

    it('renders SVG icons with inline size styles, no Tailwind classes', () => {
      const { container } = render(<Chart symbol="BTCUSDT" />)
      const fitButton = screen.getByTestId('fit-content-button')
      const svg = fitButton.querySelector('svg') as SVGElement
      expect(svg).toBeTruthy()
      // Inline width/height from tokens
      expect((svg as any).style.width).toBe(DEFAULT_TOKENS.spacing[4])
      expect((svg as any).style.height).toBe(DEFAULT_TOKENS.spacing[4])
      // No Tailwind utility classes
      const cls = (svg.getAttribute('class') || '').trim()
      expect(cls).toBe('')
    })

    it('contains no Tailwind utility class keywords in DOM', () => {
      const { container } = render(<Chart symbol="BTCUSDT" />)
      const withClass = Array.from(container.querySelectorAll('[class]')) as HTMLElement[]
      const forbidden = ['w-', 'h-', 'px-', 'py-', 'bg-', 'text-']
      withClass.forEach(el => {
        const cls = el.getAttribute('class') || ''
        forbidden.forEach(fragment => {
          expect(cls.includes(fragment)).toBe(false)
        })
      })
    })
  })
})
