import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import LoginPage from './page'

// Mock AuthContext
const mockLogin = vi.fn()
vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({
    state: { isLoading: false, isAuthenticated: false, user: null },
    login: mockLogin,
  }),
}))

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form with required elements', () => {
    render(<LoginPage />)

    expect(screen.getByTestId('login-form')).toBeInTheDocument()
    expect(screen.getByTestId('email-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
    expect(screen.getByTestId('login-button')).toBeInTheDocument()
  })

  it('shows validation error for empty email', async () => {
    render(<LoginPage />)

    fireEvent.click(screen.getByTestId('login-button'))

    await waitFor(() => {
      expect(screen.getByTestId('email-error')).toBeInTheDocument()
    })
  })

  it('shows validation error for invalid email format', async () => {
    render(<LoginPage />)

    fireEvent.change(screen.getByTestId('email-input'), { target: { value: 'invalid-email' } })
    fireEvent.submit(screen.getByTestId('login-form'))

    await waitFor(() => {
      expect(screen.getByTestId('email-error')).toHaveTextContent(/valid email/i)
    })
  })

  it('shows validation error for empty password', async () => {
    render(<LoginPage />)

    fireEvent.change(screen.getByTestId('email-input'), { target: { value: 'test@example.com' } })
    fireEvent.click(screen.getByTestId('login-button'))

    await waitFor(() => {
      expect(screen.getByTestId('password-error')).toBeInTheDocument()
    })
  })

  it('calls login on valid form submit', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginPage />)

    fireEvent.change(screen.getByTestId('email-input'), { target: { value: 'test@example.com' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'Password123' } })
    fireEvent.click(screen.getByTestId('login-button'))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'Password123')
    })
  })

  it('displays error message on login failure', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'))
    render(<LoginPage />)

    fireEvent.change(screen.getByTestId('email-input'), { target: { value: 'test@example.com' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'wrongpass' } })
    fireEvent.click(screen.getByTestId('login-button'))

    await waitFor(() => {
      expect(screen.getByTestId('login-error')).toHaveTextContent('Invalid credentials')
    })
  })

  it('handles Enter key submission', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginPage />)

    fireEvent.change(screen.getByTestId('email-input'), { target: { value: 'test@example.com' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'Password123' } })
    fireEvent.keyDown(screen.getByTestId('password-input'), { key: 'Enter' })

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalled()
    })
  })
})
