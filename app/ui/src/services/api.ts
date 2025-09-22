import { ApiClient } from './api.client'
import { getApiUrl } from '@/config/constants'

export const apiClient = new ApiClient({
  baseUrl: getApiUrl(),
})
