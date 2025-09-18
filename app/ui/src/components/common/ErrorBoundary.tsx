import React from 'react'
import { ErrorMessage } from './ErrorMessage'
import './ErrorBoundary.css'

type ErrorInfo = {
  componentStack: string
}

type ErrorBoundaryProps = {
  children: React.ReactNode
  fallback?: React.ReactNode | ((error: Error, reset: () => void) => React.ReactNode)
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  resetKeys?: Array<string | number>
  className?: string
}

type ErrorBoundaryState = {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
  showDetails: boolean
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      showDetails: false,
    }
    this.resetErrorBoundary = this.resetErrorBoundary.bind(this)
    this.toggleDetails = this.toggleDetails.bind(this)
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error details
    console.error('ErrorBoundary caught an error:', error, errorInfo)

    // Update state with error info
    this.setState({ errorInfo })

    // Call onError callback if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    const { hasError } = this.state
    const { resetKeys } = this.props

    // Check if resetKeys have changed
    if (
      hasError &&
      prevProps.resetKeys !== resetKeys &&
      resetKeys &&
      prevProps.resetKeys &&
      !this.arraysEqual(prevProps.resetKeys, resetKeys)
    ) {
      this.resetErrorBoundary()
    }
  }

  arraysEqual(a: Array<string | number>, b: Array<string | number>): boolean {
    if (a.length !== b.length) return false
    return a.every((val, index) => val === b[index])
  }

  resetErrorBoundary() {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      showDetails: false,
    })
  }

  toggleDetails() {
    this.setState(prevState => ({ showDetails: !prevState.showDetails }))
  }

  render() {
    const { hasError, error, errorInfo, showDetails } = this.state
    const { fallback, children, className } = this.props

    if (hasError && error) {
      // Custom fallback provided
      if (fallback) {
        if (typeof fallback === 'function') {
          return <>{fallback(error, this.resetErrorBoundary)}</>
        }
        return <>{fallback}</>
      }

      // Default fallback UI
      return (
        <div
          className={['error-boundary-fallback', className].filter(Boolean).join(' ')}
          data-testid="error-boundary-fallback"
        >
          <ErrorMessage
            error={error}
            variant="error"
            title="Something went wrong"
            onRetry={this.resetErrorBoundary}
            retryText="Try again"
          />

          <div className="error-details-section">
            <button type="button" className="error-details-toggle" onClick={this.toggleDetails}>
              {showDetails ? 'Hide details' : 'Show details'}
            </button>

            {showDetails && errorInfo && (
              <div className="error-details">
                <div className="error-stack">
                  <h4>Error stack:</h4>
                  <pre>{error.stack}</pre>
                </div>
                <div className="component-stack">
                  <h4>Component stack:</h4>
                  <pre>{errorInfo.componentStack}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )
    }

    // Only wrap in div if className is provided
    if (className) {
      return <div className={className}>{children}</div>
    }

    return <>{children}</>
  }
}
