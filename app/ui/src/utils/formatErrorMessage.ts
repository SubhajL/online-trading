export function formatErrorMessage(error: unknown): string {
  // Handle null/undefined/empty
  if (!error) {
    return 'An unexpected error occurred'
  }

  // Handle string errors
  if (typeof error === 'string') {
    return error || 'An unexpected error occurred'
  }

  // Handle Error instances
  if (error instanceof Error) {
    const message = error.message

    // Map specific error patterns to user-friendly messages
    if (message.includes('NetworkError') || message.includes('Failed to fetch')) {
      return 'Network connection error. Please check your internet connection.'
    }

    if (message.includes('Request timed out')) {
      return 'Request timed out. Please try again.'
    }

    if (message.includes('401 Unauthorized')) {
      return 'Authentication failed. Please log in again.'
    }

    if (message.includes('403 Forbidden')) {
      return 'You do not have permission to perform this action.'
    }

    if (message.includes('404 Not Found')) {
      return 'The requested resource was not found.'
    }

    if (message.includes('500 Internal Server Error')) {
      return 'Server error. Please try again later.'
    }

    if (message.includes('429 Too Many Requests')) {
      return 'Too many requests. Please slow down and try again.'
    }

    if (message.includes('WebSocket connection closed')) {
      return 'Connection lost. Attempting to reconnect...'
    }

    if (message === 'Insufficient balance') {
      return 'Insufficient balance to complete this transaction.'
    }

    if (message.includes('Order rejected')) {
      return 'Order was rejected. Please check your parameters and try again.'
    }

    // Return original message if no specific handling
    return message || 'An unexpected error occurred'
  }

  // Handle object errors
  if (typeof error === 'object' && error !== null) {
    // Handle axios-like errors
    if ('response' in error) {
      const response = error.response as any
      if (response?.data?.message) {
        return response.data.message
      }
      if (response?.data?.error && typeof response.data.error === 'string') {
        return response.data.error
      }
    }

    // Check common error properties
    if ('message' in error && typeof error.message === 'string') {
      return error.message
    }

    if ('error' in error && typeof error.error === 'string') {
      return error.error
    }

    if ('description' in error && typeof error.description === 'string') {
      return error.description
    }
  }

  // Default fallback
  return 'An unexpected error occurred'
}
