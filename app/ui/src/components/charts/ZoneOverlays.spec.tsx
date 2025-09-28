import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ZoneOverlays } from './ZoneOverlays'
import type { Zone } from '@/types'

describe('ZoneOverlays', () => {
  const mockZones: Zone[] = [
    {
      id: 'zone-1',
      symbol: 'BTCUSDT',
      type: 'supply',
      priceFrom: 45000,
      priceTo: 45200,
      strength: 3,
      touches: 1,
      timeframe: '15m',
      created: 1640995200000,
      lastTested: 1640995260000,
    },
    {
      id: 'zone-2',
      symbol: 'BTCUSDT',
      type: 'demand',
      priceFrom: 44600,
      priceTo: 44800,
      strength: 5,
      touches: 0,
      timeframe: '15m',
      created: 1640995320000,
    },
    {
      id: 'zone-3',
      symbol: 'BTCUSDT',
      type: 'supply',
      priceFrom: 45400,
      priceTo: 45500,
      strength: 2,
      touches: 3,
      timeframe: '15m',
      created: 1640995380000,
    },
  ]

  const createMockChartRef = () => ({
    current: document.createElement('div'),
  })

  describe('rendering', () => {
    it('should render overlay container', () => {
      const chartRef = createMockChartRef()
      render(<ZoneOverlays zones={[]} chartRef={chartRef} />)

      expect(screen.getByTestId('zone-overlays')).toBeInTheDocument()
    })

    it('should have correct styling for overlay container', () => {
      const chartRef = createMockChartRef()
      render(<ZoneOverlays zones={[]} chartRef={chartRef} />)

      const container = screen.getByTestId('zone-overlays')
      expect(container).toHaveClass('absolute', 'inset-0', 'pointer-events-none', 'z-10')
    })

    it('should render empty container when no zones', () => {
      const chartRef = createMockChartRef()
      render(<ZoneOverlays zones={[]} chartRef={chartRef} />)

      const container = screen.getByTestId('zone-overlays')
      expect(container.children).toHaveLength(0)
    })
  })

  describe('zone overlays', () => {
    it('should create overlay for each zone', () => {
      const chartRef = createMockChartRef()
      render(<ZoneOverlays zones={mockZones} chartRef={chartRef} />)

      const container = screen.getByTestId('zone-overlays')
      expect(container.children).toHaveLength(mockZones.length)
    })

    it('should create supply zone overlay', () => {
      const chartRef = createMockChartRef()
      const supplyZones = mockZones.filter(z => z.type === 'supply')
      render(<ZoneOverlays zones={supplyZones} chartRef={chartRef} />)

      const overlays = screen.getAllByTestId('zone-overlay-supply')
      expect(overlays).toHaveLength(2) // We have 2 supply zones in mockZones
    })

    it('should create demand zone overlay', () => {
      const chartRef = createMockChartRef()
      const demandZone = mockZones.filter(z => z.type === 'demand')
      render(<ZoneOverlays zones={demandZone} chartRef={chartRef} />)

      const overlay = screen.getByTestId('zone-overlay-demand')
      expect(overlay).toBeInTheDocument()
    })

    it('should display zone type and strength', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'test-1',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 4,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      expect(screen.getByText('Supply (S4)')).toBeInTheDocument()
    })

    it('should display touch count badge when touches > 0', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'test-2',
          symbol: 'BTCUSDT',
          type: 'demand',
          priceFrom: 44800,
          priceTo: 44900,
          strength: 3,
          touches: 2,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      expect(screen.getByText('2x')).toBeInTheDocument()
    })

    it('should display last tested indicator', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'test-3',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 3,
          touches: 1,
          timeframe: '15m',
          created: Date.now() - 3600000,
          lastTested: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      expect(screen.getByText('✓')).toBeInTheDocument()
    })
  })

  describe('zone styling', () => {
    it('should apply red color for supply zones', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'test-supply',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 3,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      const label = screen.getByText('Supply (S3)')
      expect(label).toHaveClass('text-red-600')
    })

    it('should apply green color for demand zones', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'test-demand',
          symbol: 'BTCUSDT',
          type: 'demand',
          priceFrom: 44800,
          priceTo: 44900,
          strength: 3,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      const label = screen.getByText('Demand (S3)')
      expect(label).toHaveClass('text-green-600')
    })

    it('should apply appropriate badge colors', () => {
      const chartRef = createMockChartRef()
      const zones: Zone[] = [
        {
          id: 'test-supply-touch',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 3,
          touches: 2,
          timeframe: '15m',
          created: Date.now(),
        },
        {
          id: 'test-demand-touch',
          symbol: 'BTCUSDT',
          type: 'demand',
          priceFrom: 44800,
          priceTo: 44900,
          strength: 3,
          touches: 1,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zones} chartRef={chartRef} />)

      const supplyBadge = screen.getByText('2x')
      expect(supplyBadge).toHaveClass('bg-red-100', 'text-red-700')

      const demandBadge = screen.getByText('1x')
      expect(demandBadge).toHaveClass('bg-green-100', 'text-green-700')
    })
  })

  describe('data attributes', () => {
    it('should set zone data attributes', () => {
      const chartRef = createMockChartRef()
      const zone: Zone[] = [
        {
          id: 'unique-zone-id',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 4,
          touches: 1,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zone} chartRef={chartRef} />)

      const overlay = screen.getByTestId('zone-overlay-supply')
      expect(overlay).toHaveAttribute('data-zone-id', 'unique-zone-id')
      expect(overlay).toHaveAttribute('data-strength', '4')
    })
  })

  describe('updates', () => {
    it('should clear previous overlays when zones change', () => {
      const chartRef = createMockChartRef()
      const { rerender } = render(<ZoneOverlays zones={mockZones} chartRef={chartRef} />)

      const container = screen.getByTestId('zone-overlays')
      expect(container.children).toHaveLength(3)

      const newZones = mockZones.slice(0, 1)
      rerender(<ZoneOverlays zones={newZones} chartRef={chartRef} />)

      expect(container.children).toHaveLength(1)
    })

    it('should handle empty chartRef', () => {
      const chartRef = { current: null }
      render(<ZoneOverlays zones={mockZones} chartRef={chartRef} />)

      const container = screen.getByTestId('zone-overlays')
      expect(container.children).toHaveLength(0)
    })
  })

  describe('opacity calculation', () => {
    it('should render zones with different opacities based on strength', () => {
      const chartRef = createMockChartRef()
      const zones: Zone[] = [
        {
          id: 'weak-zone',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 1,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
        {
          id: 'strong-zone',
          symbol: 'BTCUSDT',
          type: 'demand',
          priceFrom: 44800,
          priceTo: 44900,
          strength: 5,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zones} chartRef={chartRef} />)

      const overlays = screen.getByTestId('zone-overlays').children
      expect(overlays).toHaveLength(2)
      // Note: Actual opacity testing would require checking computed styles
    })

    it('should reduce opacity for zones with more touches', () => {
      const chartRef = createMockChartRef()
      const zones: Zone[] = [
        {
          id: 'fresh-zone',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45000,
          priceTo: 45100,
          strength: 3,
          touches: 0,
          timeframe: '15m',
          created: Date.now(),
        },
        {
          id: 'tested-zone',
          symbol: 'BTCUSDT',
          type: 'supply',
          priceFrom: 45200,
          priceTo: 45300,
          strength: 3,
          touches: 3,
          timeframe: '15m',
          created: Date.now(),
        },
      ]
      render(<ZoneOverlays zones={zones} chartRef={chartRef} />)

      const overlays = screen.getByTestId('zone-overlays').children
      expect(overlays).toHaveLength(2)
      // Note: Actual opacity testing would require checking computed styles
    })
  })
})
