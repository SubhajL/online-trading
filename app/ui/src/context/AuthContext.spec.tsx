import { renderHook, act, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

// Mock next/navigation
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Mock fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
  )

  describe('initial state', () => {
    it('provides unauthenticated state when no stored auth', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      expect(result.current.state.user).toBeNull()
      expect(result.current.state.isAuthenticated).toBe(false)
    })

    it('restores session from localStorage', async () => {
      const storedAuth = {
        user: { id: '1', username: 'trader', email: 'trader@test.com', roles: ['operator'] },
        token: 'stored-token',
      }
      localStorage.setItem('trading_auth', JSON.stringify(storedAuth))

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      expect(result.current.state.user).toEqual(storedAuth.user)
      expect(result.current.state.isAuthenticated).toBe(true)
    })
  })

  describe('login', () => {
    it('updates state on successful login', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: 'jwt-token', refreshToken: 'refresh' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123')
      })

      expect(result.current.state.isAuthenticated).toBe(true)
      expect(result.current.state.user?.email).toBe('trader@test.com')
      expect(mockPush).toHaveBeenCalledWith('/')
    })

    it('throws on invalid credentials', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ message: 'Invalid credentials' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await expect(
        act(async () => {
          await result.current.login('wrong@test.com', 'wrongpass')
        }),
      ).rejects.toThrow('Invalid credentials')

      expect(result.current.state.isAuthenticated).toBe(false)
    })

    it('stores auth in localStorage on success', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: 'jwt-token', refreshToken: 'refresh' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123')
      })

      const stored = JSON.parse(localStorage.getItem('trading_auth') || '{}')
      expect(stored.token).toBe('jwt-token')
      expect(stored.user.email).toBe('trader@test.com')
    })
  })

  describe('logout', () => {
    it('clears user and redirects to login', async () => {
      const storedAuth = {
        user: { id: '1', username: 'trader', email: 'trader@test.com', roles: ['operator'] },
        token: 'stored-token',
      }
      localStorage.setItem('trading_auth', JSON.stringify(storedAuth))

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isAuthenticated).toBe(true)
      })

      act(() => {
        result.current.logout()
      })

      expect(result.current.state.user).toBeNull()
      expect(result.current.state.isAuthenticated).toBe(false)
      expect(localStorage.getItem('trading_auth')).toBeNull()
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
  })

  it('throws error when used outside provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      renderHook(() => useAuth())
    }).toThrow('useAuth must be used within an AuthProvider')

    consoleSpy.mockRestore()
  })
})
