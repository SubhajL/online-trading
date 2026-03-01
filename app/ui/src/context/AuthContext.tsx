'use client'

import { createContext, useContext, useState, useCallback, useMemo, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { setOnUnauthorizedHandler } from '@/services/api.client'
import { websocketService } from '@/services/websocket'

type User = {
  id: string
  username: string
  email: string
  roles: string[]
}

type AuthState = {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  notification: string | null
}

type StoredAuth = {
  user: User
  token: string
  refreshToken?: string
  rememberMe?: boolean
}

type AuthContextValue = {
  state: AuthState
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>
  logout: () => void
  handleSessionExpired: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const AUTH_STORAGE_KEY = 'trading_auth'
const REFRESH_BUFFER_MS = 30000 // Refresh 30 seconds before expiry
const NOTIFICATION_TIMEOUT_MS = 5000

function decodeJwtExpiry(token: string): number | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const encodedPayload = parts[1]
    if (!encodedPayload) return null
    const payload = JSON.parse(atob(encodedPayload))
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

function getStoredAuth(): StoredAuth | null {
  if (typeof window === 'undefined') return null
  try {
    // Check localStorage first (rememberMe = true), then sessionStorage
    const localStored = localStorage.getItem(AUTH_STORAGE_KEY)
    if (localStored) return JSON.parse(localStored)
    const sessionStored = sessionStorage.getItem(AUTH_STORAGE_KEY)
    if (sessionStored) return JSON.parse(sessionStored)
    return null
  } catch {
    return null
  }
}

function setStoredAuth(user: User, token: string, refreshToken: string, rememberMe: boolean) {
  const data: StoredAuth = { user, token, refreshToken, rememberMe }
  if (rememberMe) {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data))
    sessionStorage.removeItem(AUTH_STORAGE_KEY)
  } else {
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data))
    localStorage.removeItem(AUTH_STORAGE_KEY)
  }
}

function clearStoredAuth() {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  sessionStorage.removeItem(AUTH_STORAGE_KEY)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const notificationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
    notification: null,
  })

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
  }, [])

  const refreshAccessToken = useCallback(async (refreshToken: string) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002/api'}/auth/refresh`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
      )

      if (!response.ok) {
        throw new Error('Token refresh failed')
      }

      const data = await response.json()
      return data.access_token as string
    } catch {
      return null
    }
  }, [])

  const scheduleTokenRefresh = useCallback(
    (token: string, refreshToken: string, rememberMe: boolean, user: User) => {
      clearRefreshTimer()
      const expiryMs = decodeJwtExpiry(token)
      if (!expiryMs) return

      const now = Date.now()
      const timeUntilRefresh = expiryMs - now - REFRESH_BUFFER_MS

      if (timeUntilRefresh <= 0) {
        // Token is already expired or about to expire, refresh immediately
        refreshAccessToken(refreshToken).then(newToken => {
          if (newToken) {
            setStoredAuth(user, newToken, refreshToken, rememberMe)
            scheduleTokenRefresh(newToken, refreshToken, rememberMe, user)
          }
        })
        return
      }

      refreshTimerRef.current = setTimeout(async () => {
        const newToken = await refreshAccessToken(refreshToken)
        if (newToken) {
          setStoredAuth(user, newToken, refreshToken, rememberMe)
          scheduleTokenRefresh(newToken, refreshToken, rememberMe, user)
        }
      }, timeUntilRefresh)
    },
    [clearRefreshTimer, refreshAccessToken],
  )

  // Load auth state from storage on mount
  useEffect(() => {
    const stored = getStoredAuth()
    if (stored) {
      setState({
        user: stored.user,
        isAuthenticated: true,
        isLoading: false,
        notification: null,
      })
      // Schedule token refresh if we have refresh token
      if (stored.refreshToken) {
        scheduleTokenRefresh(
          stored.token,
          stored.refreshToken,
          stored.rememberMe ?? true,
          stored.user,
        )
      }
    } else {
      setState(prev => ({ ...prev, isLoading: false }))
    }
  }, [scheduleTokenRefresh])

  // Listen for storage events from other tabs (TC1.5)
  useEffect(() => {
    const handleStorageEvent = (event: StorageEvent) => {
      if (event.key !== AUTH_STORAGE_KEY) return

      if (event.newValue) {
        // Another tab logged in
        try {
          const data: StoredAuth = JSON.parse(event.newValue)
          setState({
            user: data.user,
            isAuthenticated: true,
            isLoading: false,
            notification: null,
          })
          if (data.refreshToken) {
            scheduleTokenRefresh(data.token, data.refreshToken, data.rememberMe ?? true, data.user)
          }
        } catch {
          // Invalid JSON, ignore
        }
      } else {
        // Another tab logged out
        clearRefreshTimer()
        setState({
          user: null,
          isAuthenticated: false,
          isLoading: false,
          notification: 'Session ended in another tab',
        })
        // Clear notification after timeout
        notificationTimerRef.current = setTimeout(() => {
          setState(prev => ({ ...prev, notification: null }))
        }, NOTIFICATION_TIMEOUT_MS)
      }
    }

    window.addEventListener('storage', handleStorageEvent)
    return () => {
      window.removeEventListener('storage', handleStorageEvent)
    }
  }, [clearRefreshTimer, scheduleTokenRefresh])

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      clearRefreshTimer()
      if (notificationTimerRef.current) {
        clearTimeout(notificationTimerRef.current)
      }
    }
  }, [clearRefreshTimer])

  const login = useCallback(
    async (email: string, password: string, rememberMe = true) => {
      setState(prev => ({ ...prev, isLoading: true }))

      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002/api'}/auth/login`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: email, password, rememberMe }),
          },
        )

        if (!response.ok) {
          const error = await response.json().catch(() => ({ message: 'Login failed' }))
          throw new Error(error.message || 'Invalid credentials')
        }

        const data = await response.json()
        const user: User = {
          id: data.userId || '1',
          username: email.split('@')[0] ?? email,
          email,
          roles: data.roles || ['user'],
        }

        setStoredAuth(user, data.accessToken, data.refreshToken || '', rememberMe)
        scheduleTokenRefresh(data.accessToken, data.refreshToken || '', rememberMe, user)
        setState({
          user,
          isAuthenticated: true,
          isLoading: false,
          notification: null,
        })

        // Reconnect WebSocket with new auth token
        websocketService.reconnectWithAuth()

        router.push('/')
      } catch (error) {
        setState(prev => ({ ...prev, isLoading: false }))
        throw error
      }
    },
    [router, scheduleTokenRefresh],
  )

  const logout = useCallback(() => {
    clearRefreshTimer()
    clearStoredAuth()
    setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      notification: null,
    })
    router.push('/login')
  }, [router, clearRefreshTimer])

  const handleSessionExpired = useCallback(() => {
    clearRefreshTimer()
    clearStoredAuth()
    setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      notification: 'Session expired. Please log in again.',
    })
    router.push('/login')
  }, [router, clearRefreshTimer])

  // Register global 401 handler for API client
  useEffect(() => {
    setOnUnauthorizedHandler(handleSessionExpired)
    return () => {
      setOnUnauthorizedHandler(null)
    }
  }, [handleSessionExpired])

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      login,
      logout,
      handleSessionExpired,
    }),
    [state, login, logout, handleSessionExpired],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return context
}
