import { REQUEST_TIMEOUT } from '@/config/constants'

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  headers?: Record<string, string>
  body?: unknown
  params?: Record<string, string | number | boolean>
  timeout?: number
  retries?: number
  signal?: AbortSignal
}

export type ApiClientConfig = {
  baseUrl: string
  timeout?: number
  defaultHeaders?: Record<string, string>
}

export class ApiClient {
  private baseUrl: string
  private timeout: number
  private defaultHeaders: Record<string, string>

  constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl
    this.timeout = config.timeout ?? REQUEST_TIMEOUT
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      ...config.defaultHeaders,
    }
  }

  async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const {
      method = 'GET',
      headers = {},
      body,
      params,
      timeout = this.timeout,
      retries = 0,
      signal: customSignal,
    } = options

    // Build URL with query parameters
    let url = `${this.baseUrl}${endpoint}`
    if (params) {
      const searchParams = new URLSearchParams()
      Object.entries(params).forEach(([key, value]) => {
        searchParams.append(key, String(value))
      })
      url += `?${searchParams.toString()}`
    }

    // Handle abort signals
    let timeoutId: NodeJS.Timeout | undefined
    let signal: AbortSignal

    if (customSignal) {
      // Use the custom signal directly
      signal = customSignal
    } else {
      // Create abort controller for timeout
      const controller = new AbortController()
      timeoutId = setTimeout(() => controller.abort(), timeout)
      signal = controller.signal
    }

    try {
      const response = await fetch(url, {
        method,
        headers: {
          ...this.defaultHeaders,
          ...headers,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal,
      })

      if (timeoutId) {
        clearTimeout(timeoutId)
      }

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }

      // Check if the error is an abort error
      const isAbortError =
        error instanceof Error && (error.name === 'AbortError' || error.message.includes('aborted'))

      // Retry logic - don't retry on abort errors
      if (retries > 0 && error instanceof Error && !isAbortError) {
        // Don't pass the signal on retry to avoid immediate abort
        const { signal, ...retryOptions } = options
        return this.request(endpoint, { ...retryOptions, retries: retries - 1 })
      }

      throw error
    }
  }

  async get<T = unknown>(
    endpoint: string,
    options?: Omit<RequestOptions, 'method' | 'body'>,
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  async post<T = unknown>(
    endpoint: string,
    body?: unknown,
    options?: Omit<RequestOptions, 'method' | 'body'>,
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'POST', body })
  }

  async put<T = unknown>(
    endpoint: string,
    body?: unknown,
    options?: Omit<RequestOptions, 'method' | 'body'>,
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PUT', body })
  }

  async delete<T = unknown>(
    endpoint: string,
    options?: Omit<RequestOptions, 'method'>,
  ): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }
}
