import { describe, it, expect } from 'vitest'
import { formatErrorMessage } from './formatErrorMessage'

describe('formatErrorMessage', () => {
  it('formats Error instance with message', () => {
    const error = new Error('Something went wrong')
    expect(formatErrorMessage(error)).toBe('Something went wrong')
  })

  it('formats Error instance without message', () => {
    const error = new Error()
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats string error', () => {
    const error = 'Network connection failed'
    expect(formatErrorMessage(error)).toBe('Network connection failed')
  })

  it('formats empty string', () => {
    const error = ''
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats network error', () => {
    const error = new Error('NetworkError: Failed to fetch')
    expect(formatErrorMessage(error)).toBe(
      'Network connection error. Please check your internet connection.',
    )
  })

  it('formats timeout error', () => {
    const error = new Error('Request timed out')
    expect(formatErrorMessage(error)).toBe('Request timed out. Please try again.')
  })

  it('formats unauthorized error', () => {
    const error = new Error('401 Unauthorized')
    expect(formatErrorMessage(error)).toBe('Authentication failed. Please log in again.')
  })

  it('formats forbidden error', () => {
    const error = new Error('403 Forbidden')
    expect(formatErrorMessage(error)).toBe('You do not have permission to perform this action.')
  })

  it('formats not found error', () => {
    const error = new Error('404 Not Found')
    expect(formatErrorMessage(error)).toBe('The requested resource was not found.')
  })

  it('formats server error', () => {
    const error = new Error('500 Internal Server Error')
    expect(formatErrorMessage(error)).toBe('Server error. Please try again later.')
  })

  it('formats rate limit error', () => {
    const error = new Error('429 Too Many Requests')
    expect(formatErrorMessage(error)).toBe('Too many requests. Please slow down and try again.')
  })

  it('formats validation error', () => {
    const error = new Error('Validation failed: Invalid quantity')
    expect(formatErrorMessage(error)).toBe('Validation failed: Invalid quantity')
  })

  it('formats object error with message property', () => {
    const error = { message: 'Custom error message' }
    expect(formatErrorMessage(error)).toBe('Custom error message')
  })

  it('formats object error with error property', () => {
    const error = { error: 'API error occurred' }
    expect(formatErrorMessage(error)).toBe('API error occurred')
  })

  it('formats object error with description property', () => {
    const error = { description: 'Detailed error description' }
    expect(formatErrorMessage(error)).toBe('Detailed error description')
  })

  it('formats nested error object', () => {
    const error = {
      response: {
        data: {
          message: 'Server response error',
        },
      },
    }
    expect(formatErrorMessage(error)).toBe('Server response error')
  })

  it('formats axios-like error', () => {
    const error = {
      response: {
        status: 400,
        data: {
          error: 'Bad Request',
          message: 'Invalid parameters',
        },
      },
    }
    expect(formatErrorMessage(error)).toBe('Invalid parameters')
  })

  it('formats null error', () => {
    const error = null
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats undefined error', () => {
    const error = undefined
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats number error', () => {
    const error = 404
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats boolean error', () => {
    const error = false
    expect(formatErrorMessage(error)).toBe('An unexpected error occurred')
  })

  it('formats WebSocket close event', () => {
    const error = new Error('WebSocket connection closed')
    expect(formatErrorMessage(error)).toBe('Connection lost. Attempting to reconnect...')
  })

  it('formats insufficient balance error', () => {
    const error = new Error('Insufficient balance')
    expect(formatErrorMessage(error)).toBe('Insufficient balance to complete this transaction.')
  })

  it('formats order rejected error', () => {
    const error = new Error('Order rejected by exchange')
    expect(formatErrorMessage(error)).toBe(
      'Order was rejected. Please check your parameters and try again.',
    )
  })

  it('preserves user-friendly messages', () => {
    const error = new Error('Please enter a valid quantity')
    expect(formatErrorMessage(error)).toBe('Please enter a valid quantity')
  })

  it('handles complex error chain', () => {
    const error = {
      cause: {
        message: 'Root cause error',
      },
      message: 'High level error',
    }
    expect(formatErrorMessage(error)).toBe('High level error')
  })
})
