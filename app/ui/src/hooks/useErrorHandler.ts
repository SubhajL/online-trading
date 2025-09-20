import { useState, useCallback, useRef, useEffect } from 'react'
import { formatErrorMessage } from '../utils/formatErrorMessage'

type UseErrorHandlerOptions = {
  logErrors?: boolean
  onError?: (error: unknown) => void
  autoClear?: number
  formatError?: (error: unknown) => string
}

type UseErrorHandlerReturn = {
  error: unknown
  errorMessage?: string
  isError: boolean
  showError: (error: unknown) => void
  clearError: () => void
  handleError: <T extends (...args: unknown[]) => unknown>(
    fn: T,
  ) => (
    ...args: Parameters<T>
  ) => ReturnType<T> extends Promise<infer U> ? Promise<U> : ReturnType<T>
  retry: () => Promise<unknown>
}

export function useErrorHandler(options: UseErrorHandlerOptions = {}): UseErrorHandlerReturn {
  const { logErrors = true, onError, autoClear, formatError = formatErrorMessage } = options

  const [error, setError] = useState<unknown>(null)
  const timeoutRef = useRef<NodeJS.Timeout>()
  const lastFunctionRef = useRef<{ fn: (...args: unknown[]) => unknown; args: unknown[] }>()

  const isError = error !== null

  const showError = useCallback(
    (err: unknown) => {
      setError(err)

      if (logErrors && err) {
        console.error('Error:', err)
      }

      if (onError) {
        onError(err)
      }

      // Set up auto-clear timeout if specified
      if (autoClear && autoClear > 0) {
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current)
        }

        timeoutRef.current = setTimeout(() => {
          setError(null)
        }, autoClear)
      }
    },
    [logErrors, onError, autoClear],
  )

  const clearError = useCallback(() => {
    setError(null)

    // Clear any pending auto-clear timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = undefined
    }
  }, [])

  const handleError = useCallback(
    <T extends (...args: unknown[]) => unknown>(fn: T) => {
      return ((...args: Parameters<T>) => {
        // Store the function and args for retry
        lastFunctionRef.current = { fn, args }

        try {
          const result = fn(...args)

          // Handle async functions
          if (result && typeof (result as any).then === 'function') {
            return (result as Promise<any>).catch((err: unknown) => {
              showError(err)
              throw err
            }) as ReturnType<T> extends Promise<infer U> ? Promise<U> : ReturnType<T>
          }

          return result as ReturnType<T> extends Promise<infer U> ? Promise<U> : ReturnType<T>
        } catch (err) {
          showError(err)
          throw err
        }
      }) as (
        ...args: Parameters<T>
      ) => ReturnType<T> extends Promise<infer U> ? Promise<U> : ReturnType<T>
    },
    [showError],
  )

  const retry = useCallback(async () => {
    if (!lastFunctionRef.current) {
      throw new Error('No function to retry')
    }

    clearError()

    const { fn, args } = lastFunctionRef.current

    try {
      const result = await fn(...args)
      return result
    } catch (err) {
      showError(err)
      throw err
    }
  }, [clearError, showError])

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  const errorMessage = error ? formatError(error) : undefined

  return {
    error,
    errorMessage,
    isError,
    showError,
    clearError,
    handleError,
    retry,
  }
}
