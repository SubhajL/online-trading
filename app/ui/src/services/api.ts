import { ApiClient } from './api.client'
import { getApiUrl } from '@/config/constants'

const AUTH_STORAGE_KEY = 'trading_auth'

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const localStored = localStorage.getItem(AUTH_STORAGE_KEY)
    if (localStored) {
      const data = JSON.parse(localStored)
      return data.token || null
    }
    const sessionStored = sessionStorage.getItem(AUTH_STORAGE_KEY)
    if (sessionStored) {
      const data = JSON.parse(sessionStored)
      return data.token || null
    }
    return null
  } catch {
    return null
  }
}

// Create API client with auth token getter
class AuthenticatedApiClient extends ApiClient {
  async request<T = unknown>(
    endpoint: string,
    options: Parameters<ApiClient['request']>[1] = {},
  ): Promise<T> {
    const token = getAuthToken()
    const headers = {
      ...options.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
    return super.request<T>(endpoint, { ...options, headers })
  }
}

export const apiClient = new AuthenticatedApiClient({
  baseUrl: getApiUrl(),
})
