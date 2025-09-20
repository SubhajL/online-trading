import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useErrorHandler } from './useErrorHandler'

// Mock console.error
const originalError = console.error

describe('useErrorHandler', () => {
  beforeEach(() => {
    console.error = vi.fn()
  })

  afterEach(() => {
    console.error = originalError
  })

  it('initializes with no error', () => {
    const { result } = renderHook(() => useErrorHandler())

    expect(result.current.error).toBeNull()
    expect(result.current.isError).toBe(false)
  })

  it('shows error when showError is called with string', () => {
    const { result } = renderHook(() => useErrorHandler())

    act(() => {
      result.current.showError('Test error message')
    })

    expect(result.current.error).toBe('Test error message')
    expect(result.current.isError).toBe(true)
  })

  it('shows error when showError is called with Error object', () => {
    const { result } = renderHook(() => useErrorHandler())
    const error = new Error('Test error')

    act(() => {
      result.current.showError(error)
    })

    expect(result.current.error).toBe(error)
    expect(result.current.isError).toBe(true)
  })

  it('clears error when clearError is called', () => {
    const { result } = renderHook(() => useErrorHandler())

    // First set an error
    act(() => {
      result.current.showError('Test error')
    })

    expect(result.current.isError).toBe(true)

    // Then clear it
    act(() => {
      result.current.clearError()
    })

    expect(result.current.error).toBeNull()
    expect(result.current.isError).toBe(false)
  })

  it('handles async errors with handleError', async () => {
    const { result } = renderHook(() => useErrorHandler())

    const asyncFunction = async () => {
      throw new Error('Async error')
    }

    await act(async () => {
      try {
        await result.current.handleError(asyncFunction)()
      } catch {
        // Expected to throw
      }
    })

    expect(result.current.error).toBeInstanceOf(Error)
    expect((result.current.error as Error)?.message).toBe('Async error')
    expect(result.current.isError).toBe(true)
  })

  it('returns result when async function succeeds', async () => {
    const { result } = renderHook(() => useErrorHandler())

    const asyncFunction = async () => {
      return 'Success result'
    }

    let functionResult

    await act(async () => {
      functionResult = await result.current.handleError(asyncFunction)()
    })

    expect(functionResult).toBe('Success result')
    expect(result.current.error).toBeNull()
    expect(result.current.isError).toBe(false)
  })

  it('logs error when logErrors option is true', () => {
    const { result } = renderHook(() => useErrorHandler({ logErrors: true }))
    const error = new Error('Test error')

    act(() => {
      result.current.showError(error)
    })

    expect(console.error).toHaveBeenCalledWith('Error:', error)
  })

  it('does not log error when logErrors option is false', () => {
    const { result } = renderHook(() => useErrorHandler({ logErrors: false }))
    const error = new Error('Test error')

    act(() => {
      result.current.showError(error)
    })

    expect(console.error).not.toHaveBeenCalled()
  })

  it('calls onError callback when error occurs', () => {
    const onError = vi.fn()
    const { result } = renderHook(() => useErrorHandler({ onError }))
    const error = new Error('Test error')

    act(() => {
      result.current.showError(error)
    })

    expect(onError).toHaveBeenCalledWith(error)
  })

  it('provides retry functionality', async () => {
    const { result } = renderHook(() => useErrorHandler())

    let attemptCount = 0
    const flakeyFunction = async () => {
      attemptCount++
      if (attemptCount < 2) {
        throw new Error('First attempt fails')
      }
      return 'Success on retry'
    }

    // First attempt fails
    await act(async () => {
      try {
        await result.current.handleError(flakeyFunction)()
      } catch {
        // Expected to throw
      }
    })

    expect(result.current.isError).toBe(true)

    // Retry succeeds
    let retryResult
    await act(async () => {
      retryResult = await result.current.retry()
    })

    expect(retryResult).toBe('Success on retry')
    expect(result.current.isError).toBe(false)
  })

  it('clears error after timeout when autoClear is set', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useErrorHandler({ autoClear: 3000 }))

    act(() => {
      result.current.showError('Test error')
    })

    expect(result.current.isError).toBe(true)

    // Fast-forward time
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.isError).toBe(false)

    vi.useRealTimers()
  })

  it('cancels auto-clear when error is manually cleared', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useErrorHandler({ autoClear: 3000 }))

    act(() => {
      result.current.showError('Test error')
    })

    act(() => {
      result.current.clearError()
    })

    // Fast-forward time - should not cause any issues
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.isError).toBe(false)

    vi.useRealTimers()
  })

  it('handles multiple errors in sequence', () => {
    const { result } = renderHook(() => useErrorHandler())

    act(() => {
      result.current.showError('First error')
    })

    expect(result.current.error).toBe('First error')

    act(() => {
      result.current.showError('Second error')
    })

    expect(result.current.error).toBe('Second error')
  })

  it('wraps synchronous functions with error handling', () => {
    const { result } = renderHook(() => useErrorHandler())

    const syncFunction = () => {
      throw new Error('Sync error')
    }

    act(() => {
      try {
        result.current.handleError(syncFunction)()
      } catch {
        // Expected to throw
      }
    })

    expect((result.current.error as Error)?.message).toBe('Sync error')
    expect(result.current.isError).toBe(true)
  })

  it('preserves function arguments when wrapping', async () => {
    const { result } = renderHook(() => useErrorHandler())

    const asyncFunction = async (a: number, b: number) => {
      return a + b
    }

    let functionResult

    await act(async () => {
      functionResult = await result.current.handleError(asyncFunction)(5, 3)
    })

    expect(functionResult).toBe(8)
  })

  it('returns wrapped function that maintains this context', async () => {
    const { result } = renderHook(() => useErrorHandler())

    class TestClass {
      value = 10

      async getValue() {
        return this.value
      }
    }

    const instance = new TestClass()
    const wrappedGetValue = result.current.handleError(instance.getValue.bind(instance))

    let functionResult
    await act(async () => {
      functionResult = await wrappedGetValue()
    })

    expect(functionResult).toBe(10)
  })

  it('provides error state for conditional rendering', () => {
    const { result } = renderHook(() => useErrorHandler())

    expect(result.current.isError).toBe(false)

    act(() => {
      result.current.showError('Error for UI')
    })

    expect(result.current.isError).toBe(true)
  })

  it('formats error message when formatError option is provided', () => {
    const formatError = (error: unknown) => {
      if (error instanceof Error) {
        return `Formatted: ${error.message}`
      }
      return String(error)
    }

    const { result } = renderHook(() => useErrorHandler({ formatError }))
    const error = new Error('Original error')

    act(() => {
      result.current.showError(error)
    })

    expect(result.current.errorMessage).toBe('Formatted: Original error')
  })
})
