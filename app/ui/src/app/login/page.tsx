'use client'

import { useState, useCallback, useEffect } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/context/AuthContext'
import styles from './login.module.css'

type FormErrors = {
  email?: string
  password?: string
}

function validateEmail(email: string): string | undefined {
  if (!email.trim()) return 'Email is required'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Please enter a valid email'
  return undefined
}

function validatePassword(password: string): string | undefined {
  if (!password) return 'Password is required'
  return undefined
}

export default function LoginPage() {
  const router = useRouter()
  const { login, state } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Redirect if already authenticated
  useEffect(() => {
    if (state.isAuthenticated && !state.isLoading) {
      router.push('/')
    }
  }, [state.isAuthenticated, state.isLoading, router])

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault()
      setLoginError(null)

      const emailError = validateEmail(email)
      const passwordError = validatePassword(password)

      if (emailError || passwordError) {
        setErrors({ email: emailError, password: passwordError })
        return
      }

      setErrors({})
      setIsSubmitting(true)

      try {
        await login(email, password)
      } catch (err) {
        setLoginError(err instanceof Error ? err.message : 'Login failed')
      } finally {
        setIsSubmitting(false)
      }
    },
    [email, password, login],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSubmit()
      }
    },
    [handleSubmit],
  )

  const isLoading = isSubmitting || state.isLoading

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>Trading Platform</h1>
        <p className={styles.subtitle}>Sign in to your account</p>

        <form data-testid="login-form" onSubmit={handleSubmit} className={styles.form}>
          {loginError && (
            <div data-testid="login-error" className={styles.errorBanner}>
              {loginError}
            </div>
          )}

          <div className={styles.field}>
            <label htmlFor="email" className={styles.label}>
              Email
            </label>
            <input
              id="email"
              type="email"
              data-testid="email-input"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className={`${styles.input} ${errors.email ? styles.inputError : ''}`}
              placeholder="trader@test.com"
              autoComplete="email"
              disabled={isLoading}
            />
            {errors.email && (
              <span data-testid="email-error" className={styles.fieldError}>
                {errors.email}
              </span>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="password" className={styles.label}>
              Password
            </label>
            <input
              id="password"
              type="password"
              data-testid="password-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              className={`${styles.input} ${errors.password ? styles.inputError : ''}`}
              placeholder="••••••••"
              autoComplete="current-password"
              disabled={isLoading}
            />
            {errors.password && (
              <span data-testid="password-error" className={styles.fieldError}>
                {errors.password}
              </span>
            )}
          </div>

          <button
            type="submit"
            data-testid="login-button"
            className={styles.button}
            disabled={isLoading}
          >
            {isLoading && <span data-testid="login-loading" className={styles.spinner} />}
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
