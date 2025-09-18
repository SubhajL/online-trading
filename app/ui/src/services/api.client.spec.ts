import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ApiClient } from './api.client'

// Mock fetch
global.fetch = vi.fn()

describe('ApiClient', () => {
  let client: ApiClient

  beforeEach(() => {
    client = new ApiClient({
      baseUrl: 'http://localhost:3000/api',
      timeout: 5000,
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('request', () => {
    it('makes successful GET request', async () => {
      const mockResponse = { data: 'test' }
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      } as Response)

      const result = await client.request('/test')

      expect(fetch).toHaveBeenCalledWith('http://localhost:3000/api/test', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: expect.any(AbortSignal),
      })

      expect(result).toEqual(mockResponse)
    })

    it('makes POST request with body', async () => {
      const requestBody = { name: 'test' }
      const mockResponse = { id: 1 }

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => mockResponse,
      } as Response)

      const result = await client.request('/test', {
        method: 'POST',
        body: requestBody,
      })

      expect(fetch).toHaveBeenCalledWith('http://localhost:3000/api/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: expect.any(AbortSignal),
      })

      expect(result).toEqual(mockResponse)
    })

    it('handles network errors', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new Error('Network error'))

      await expect(client.request('/test')).rejects.toThrow('Network error')
    })

    it('handles HTTP error responses', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ message: 'Resource not found' }),
      } as Response)

      await expect(client.request('/test')).rejects.toThrow('HTTP error! status: 404')
    })

    it.skip('respects timeout', async () => {
      // Create a client with a short timeout
      const shortTimeoutClient = new ApiClient({
        baseUrl: 'http://localhost:3000/api',
        timeout: 100,
      })

      // Mock fetch to delay longer than timeout
      vi.mocked(fetch).mockImplementationOnce(async () => {
        await new Promise(resolve => setTimeout(resolve, 200))
        return {
          ok: true,
          json: async () => ({ data: 'test' }),
        } as Response
      })

      await expect(shortTimeoutClient.request('/test')).rejects.toThrow()
    }, 10000)

    it('retries failed requests', async () => {
      vi.mocked(fetch)
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ data: 'test' }),
        } as Response)

      const result = await client.request('/test', { retries: 1 })

      expect(fetch).toHaveBeenCalledTimes(2)
      expect(result).toEqual({ data: 'test' })
    })

    it('adds custom headers', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'test' }),
      } as Response)

      await client.request('/test', {
        headers: {
          Authorization: 'Bearer token123',
        },
      })

      expect(fetch).toHaveBeenCalledWith('http://localhost:3000/api/test', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer token123',
        },
        signal: expect.any(AbortSignal),
      })
    })

    it('handles query parameters', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'test' }),
      } as Response)

      await client.request('/test', {
        params: {
          foo: 'bar',
          baz: 123,
        },
      })

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/test?foo=bar&baz=123',
        expect.any(Object),
      )
    })
  })

  describe('convenience methods', () => {
    it('provides GET method', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'test' }),
      } as Response)

      await client.get('/test')

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/test',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    it('provides POST method', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ id: 1 }),
      } as Response)

      await client.post('/test', { name: 'test' })

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/test',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'test' }),
        }),
      )
    })

    it('provides PUT method', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 1 }),
      } as Response)

      await client.put('/test/1', { name: 'updated' })

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/test/1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ name: 'updated' }),
        }),
      )
    })

    it('provides DELETE method', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: async () => ({}),
      } as Response)

      await client.delete('/test/1')

      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/test/1',
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })
})
