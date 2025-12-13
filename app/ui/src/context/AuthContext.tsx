'use client'

import { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useRouter } from 'next/navigation'

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
}

type AuthContextValue = {
  state: AuthState
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const AUTH_STORAGE_KEY = 'trading_auth'

function getStoredAuth(): { user: User; token: string } | null {
  if (typeof window === 'undefined') return null
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY)
    return stored ? JSON.parse(stored) : null
  } catch {
    return null
  }
}

function setStoredAuth(user: User, token: string) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ user, token }))
}

function clearStoredAuth() {
  localStorage.removeItem(AUTH_STORAGE_KEY)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
  })

  // Load auth state from localStorage on mount
  useEffect(() => {
    const stored = getStoredAuth()
    if (stored) {
      setState({
        user: stored.user,
        isAuthenticated: true,
        isLoading: false,
      })
    } else {
      setState(prev => ({ ...prev, isLoading: false }))
    }
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      setState(prev => ({ ...prev, isLoading: true }))

      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002/api'}/auth/login`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: email, password }),
          },
        )

        if (!response.ok) {
          const error = await response.json().catch(() => ({ message: 'Login failed' }))
          throw new Error(error.message || 'Invalid credentials')
        }

        const data = await response.json()
        const user: User = {
          id: data.userId || '1',
          username: email.split('@')[0],
          email,
          roles: data.roles || ['user'],
        }

        setStoredAuth(user, data.accessToken)
        setState({
          user,
          isAuthenticated: true,
          isLoading: false,
        })

        router.push('/')
      } catch (error) {
        setState(prev => ({ ...prev, isLoading: false }))
        throw error
      }
    },
    [router],
  )

  const logout = useCallback(() => {
    clearStoredAuth()
    setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    })
    router.push('/login')
  }, [router])

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      login,
      logout,
    }),
    [state, login, logout],
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
