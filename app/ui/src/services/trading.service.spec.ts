import { describe, it, expect, beforeEach, vi } from 'vitest'
import { TradingService } from './trading.service'
import { ApiClient } from './api.client'
import type { Order, Position, OrderId, Symbol, Venue } from '@/types'

vi.mock('./api.client')

describe('TradingService', () => {
  let service: TradingService
  let mockApiClient: ApiClient

  beforeEach(() => {
    mockApiClient = new ApiClient({ baseUrl: 'http://localhost:3000/api' })
    vi.mocked(ApiClient).mockImplementation(() => mockApiClient)

    mockApiClient.post = vi.fn()
    mockApiClient.get = vi.fn()
    mockApiClient.delete = vi.fn()

    service = new TradingService(mockApiClient)
  })

  describe('placeOrder', () => {
    it('places a market order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT' as Symbol,
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        venue: 'USD_M' as Venue,
      }

      const mockResponse: Order = {
        orderId: '12345' as OrderId,
        symbol: 'BTCUSDT' as Symbol,
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        status: 'NEW',
        venue: 'USD_M',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }

      vi.mocked(mockApiClient.post).mockResolvedValueOnce(mockResponse)

      const result = await service.placeOrder(orderRequest)

      expect(mockApiClient.post).toHaveBeenCalledWith('/trading/orders', orderRequest)
      expect(result).toEqual(mockResponse)
    })

    it('places a limit order with price', async () => {
      const orderRequest = {
        symbol: 'ETHUSDT' as Symbol,
        side: 'SELL' as const,
        type: 'LIMIT' as const,
        quantity: 1,
        price: 3000,
        venue: 'SPOT' as Venue,
      }

      const mockResponse: Order = {
        orderId: '67890' as OrderId,
        symbol: 'ETHUSDT' as Symbol,
        side: 'SELL',
        type: 'LIMIT',
        quantity: 1,
        price: 3000,
        status: 'NEW',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }

      vi.mocked(mockApiClient.post).mockResolvedValueOnce(mockResponse)

      const result = await service.placeOrder(orderRequest)

      expect(mockApiClient.post).toHaveBeenCalledWith('/trading/orders', orderRequest)
      expect(result).toEqual(mockResponse)
    })

    it('validates order parameters', async () => {
      const invalidOrder = {
        symbol: 'BTCUSDT' as Symbol,
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.01,
        // Missing price for LIMIT order
        venue: 'USD_M' as Venue,
      }

      await expect(service.placeOrder(invalidOrder)).rejects.toThrow('LIMIT order requires price')
    })

    it('validates quantity is positive', async () => {
      const invalidOrder = {
        symbol: 'BTCUSDT' as Symbol,
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: -0.01,
        venue: 'USD_M' as Venue,
      }

      await expect(service.placeOrder(invalidOrder)).rejects.toThrow('Quantity must be positive')
    })
  })

  describe('getPositions', () => {
    it('fetches current positions', async () => {
      const mockPositions: Position[] = [
        {
          symbol: 'BTCUSDT' as Symbol,
          side: 'BUY',
          quantity: 0.01,
          entryPrice: 50000,
          markPrice: 51000,
          pnl: 10,
          pnlPercent: 2,
          venue: 'USD_M',
        },
      ]

      vi.mocked(mockApiClient.get).mockResolvedValueOnce(mockPositions)

      const result = await service.getPositions()

      expect(mockApiClient.get).toHaveBeenCalledWith('/trading/positions')
      expect(result).toEqual(mockPositions)
    })

    it('handles empty positions', async () => {
      vi.mocked(mockApiClient.get).mockResolvedValueOnce([])

      const result = await service.getPositions()

      expect(result).toEqual([])
    })
  })

  describe('cancelOrder', () => {
    it('cancels an order successfully', async () => {
      const orderId = '12345' as OrderId
      const cancelRequest = {
        symbol: 'BTCUSDT' as Symbol,
        venue: 'USD_M' as Venue,
      }

      const mockResponse = {
        orderId,
        status: 'CANCELED',
      }

      vi.mocked(mockApiClient.delete).mockResolvedValueOnce(mockResponse)

      const result = await service.cancelOrder(orderId, cancelRequest)

      expect(mockApiClient.delete).toHaveBeenCalledWith(`/trading/orders/${orderId}`, {
        body: cancelRequest,
      })
      expect(result).toEqual(mockResponse)
    })
  })

  describe('getOrderStatus', () => {
    it('retrieves order status', async () => {
      const orderId = '12345' as OrderId
      const venue = 'USD_M' as Venue

      const mockOrder: Order = {
        orderId,
        symbol: 'BTCUSDT' as Symbol,
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        status: 'FILLED',
        venue,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0.01,
        avgPrice: 50000,
      }

      vi.mocked(mockApiClient.get).mockResolvedValueOnce(mockOrder)

      const result = await service.getOrderStatus(orderId, venue)

      expect(mockApiClient.get).toHaveBeenCalledWith(`/trading/orders/${orderId}`, {
        params: { venue },
      })
      expect(result).toEqual(mockOrder)
    })
  })

  describe('getActiveOrders', () => {
    it('fetches active orders', async () => {
      const mockOrders: Order[] = [
        {
          orderId: '12345' as OrderId,
          symbol: 'BTCUSDT' as Symbol,
          side: 'BUY',
          type: 'LIMIT',
          quantity: 0.01,
          price: 49000,
          status: 'NEW',
          venue: 'USD_M',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ]

      vi.mocked(mockApiClient.get).mockResolvedValueOnce(mockOrders)

      const result = await service.getActiveOrders()

      expect(mockApiClient.get).toHaveBeenCalledWith('/trading/orders')
      expect(result).toEqual(mockOrders)
    })
  })

  describe('setAutoTrading', () => {
    it('enables auto trading', async () => {
      const mockResponse = { enabled: true, message: 'Auto trading enabled' }

      vi.mocked(mockApiClient.post).mockResolvedValueOnce(mockResponse)

      const result = await service.setAutoTrading(true)

      expect(mockApiClient.post).toHaveBeenCalledWith('/trading/auto-trading', {
        enabled: true,
      })
      expect(result).toEqual(mockResponse)
    })

    it('disables auto trading', async () => {
      const mockResponse = { enabled: false, message: 'Auto trading disabled' }

      vi.mocked(mockApiClient.post).mockResolvedValueOnce(mockResponse)

      const result = await service.setAutoTrading(false)

      expect(mockApiClient.post).toHaveBeenCalledWith('/trading/auto-trading', {
        enabled: false,
      })
      expect(result).toEqual(mockResponse)
    })
  })

  describe('getAutoTradingStatus', () => {
    it('retrieves auto trading status', async () => {
      const mockStatus = { enabled: true }

      vi.mocked(mockApiClient.get).mockResolvedValueOnce(mockStatus)

      const result = await service.getAutoTradingStatus()

      expect(mockApiClient.get).toHaveBeenCalledWith('/trading/auto-trading')
      expect(result).toEqual(mockStatus)
    })
  })
})
