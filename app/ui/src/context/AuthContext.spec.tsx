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
    sessionStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    sessionStorage.clear()
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

  describe('TC1.4 - token refresh', () => {
    it('schedules token refresh before expiry', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      // Create a JWT that expires in 60 seconds
      const expTime = Math.floor(Date.now() / 1000) + 60
      const payload = btoa(JSON.stringify({ exp: expTime }))
      const mockJwt = `header.${payload}.signature`

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: mockJwt, refreshToken: 'refresh-token' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      // Wait for initial load
      await vi.runOnlyPendingTimersAsync()

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123')
      })

      // Setup mock for refresh call
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ access_token: 'new-token' }),
      })

      // Advance time to trigger refresh (30s mark)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(31000)
      })

      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(mockFetch).toHaveBeenLastCalledWith(
        expect.stringContaining('/auth/refresh'),
        expect.objectContaining({ method: 'POST' }),
      )

      vi.useRealTimers()
    })

    it('clears refresh timer on logout', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      const expTime = Math.floor(Date.now() / 1000) + 60
      const payload = btoa(JSON.stringify({ exp: expTime }))
      const mockJwt = `header.${payload}.signature`

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: mockJwt, refreshToken: 'refresh-token' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await vi.runOnlyPendingTimersAsync()

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123')
      })

      act(() => {
        result.current.logout()
      })

      // Advance time past refresh threshold
      await act(async () => {
        await vi.advanceTimersByTimeAsync(31000)
      })

      // Should only have login call, no refresh call after logout
      expect(mockFetch).toHaveBeenCalledTimes(1)

      vi.useRealTimers()
    })
  })

  describe('TC1.5 - multi-tab sync', () => {
    it('syncs auth state when storage changes from another tab', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      // Simulate login from another tab
      const newAuth = {
        user: { id: '2', username: 'other', email: 'other@test.com', roles: ['operator'] },
        token: 'other-token',
        refreshToken: 'other-refresh',
      }
      localStorage.setItem('trading_auth', JSON.stringify(newAuth))

      // Trigger storage event (simulating another tab)
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'trading_auth',
            newValue: JSON.stringify(newAuth),
            storageArea: localStorage,
          }),
        )
      })

      await waitFor(() => {
        expect(result.current.state.isAuthenticated).toBe(true)
        expect(result.current.state.user?.email).toBe('other@test.com')
      })
    })

    it('logs out when storage is cleared from another tab', async () => {
      const storedAuth = {
        user: { id: '1', username: 'trader', email: 'trader@test.com', roles: ['operator'] },
        token: 'stored-token',
      }
      localStorage.setItem('trading_auth', JSON.stringify(storedAuth))

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isAuthenticated).toBe(true)
      })

      // Simulate logout from another tab
      localStorage.removeItem('trading_auth')
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'trading_auth',
            newValue: null,
            storageArea: localStorage,
          }),
        )
      })

      await waitFor(() => {
        expect(result.current.state.isAuthenticated).toBe(false)
        expect(result.current.state.notification).toBe('Session ended in another tab')
      })
    })

    it('clears notification after timeout', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      const storedAuth = {
        user: { id: '1', username: 'trader', email: 'trader@test.com', roles: ['operator'] },
        token: 'stored-token',
      }
      localStorage.setItem('trading_auth', JSON.stringify(storedAuth))

      const { result } = renderHook(() => useAuth(), { wrapper })

      await vi.runOnlyPendingTimersAsync()

      expect(result.current.state.isAuthenticated).toBe(true)

      localStorage.removeItem('trading_auth')
      act(() => {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'trading_auth',
            newValue: null,
            storageArea: localStorage,
          }),
        )
      })

      expect(result.current.state.notification).toBe('Session ended in another tab')

      // Advance time to clear notification (5 seconds)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })

      expect(result.current.state.notification).toBeNull()

      vi.useRealTimers()
    })
  })

  describe('TC1.7 - remember me', () => {
    it('stores in localStorage when rememberMe is true', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: 'jwt-token', refreshToken: 'refresh' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123', true)
      })

      expect(localStorage.getItem('trading_auth')).not.toBeNull()
      expect(sessionStorage.getItem('trading_auth')).toBeNull()
    })

    it('stores in sessionStorage when rememberMe is false', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: 'jwt-token', refreshToken: 'refresh' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123', false)
      })

      expect(sessionStorage.getItem('trading_auth')).not.toBeNull()
      expect(localStorage.getItem('trading_auth')).toBeNull()
    })

    it('restores session from sessionStorage', async () => {
      const storedAuth = {
        user: { id: '1', username: 'trader', email: 'trader@test.com', roles: ['operator'] },
        token: 'session-token',
      }
      sessionStorage.setItem('trading_auth', JSON.stringify(storedAuth))

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      expect(result.current.state.user).toEqual(storedAuth.user)
      expect(result.current.state.isAuthenticated).toBe(true)
    })

    it('sends rememberMe flag to login endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ accessToken: 'jwt-token', refreshToken: 'refresh' }),
      })

      const { result } = renderHook(() => useAuth(), { wrapper })

      await waitFor(() => {
        expect(result.current.state.isLoading).toBe(false)
      })

      await act(async () => {
        await result.current.login('trader@test.com', 'Password123', true)
      })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/login'),
        expect.objectContaining({
          body: JSON.stringify({
            username: 'trader@test.com',
            password: 'Password123',
            rememberMe: true,
          }),
        }),
      )
    })
  })
})
