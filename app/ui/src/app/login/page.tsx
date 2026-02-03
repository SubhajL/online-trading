'use client'

import { useState, useCallback, useEffect } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, AlertCircle, AlertTriangle } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

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
  const [rememberMe, setRememberMe] = useState(true)
  const [errors, setErrors] = useState<FormErrors>({})
  const [loginError, setLoginError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

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
        await login(email, password, rememberMe)
      } catch (err) {
        setLoginError(err instanceof Error ? err.message : 'Login failed')
      } finally {
        setIsSubmitting(false)
      }
    },
    [email, password, rememberMe, login],
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
    <div className="relative min-h-screen bg-[#FAFBFC]">
      {/* Subtle background accents */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_circle_at_20%_20%,hsl(var(--primary)/0.18),transparent_55%),radial-gradient(700px_circle_at_80%_70%,hsl(var(--primary)/0.10),transparent_60%)]"
      />

      <div className="relative mx-auto grid min-h-screen w-full max-w-[1200px] grid-cols-1 lg:grid-cols-2">
        {/* Left (brand) panel */}
        <div className="hidden lg:flex flex-col justify-between p-10">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-card/60 px-3 py-1 text-xs text-slate-600">
              <span className="h-2 w-2 rounded-full bg-primary" />
              Real-time monitoring • Guarded execution • Audit-friendly
            </div>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-slate-900">
              Trading Platform
            </h1>
            <p className="mt-3 max-w-[46ch] text-base text-slate-600">
              A fast, safety-first surface for monitoring, decisions, and execution — designed for
              long sessions.
            </p>

            <div className="mt-8 grid gap-3">
              {[
                { title: 'Safety-first UI', desc: 'Guards and exposure always visible.' },
                { title: 'Keyboard accelerators', desc: 'Command palette and quick actions.' },
                { title: 'Clear states', desc: 'Loading, error, and offline are explicit.' },
              ].map(item => (
                <div key={item.title} className="rounded-lg border border-slate-200 bg-card/60 p-4">
                  <div className="text-sm font-semibold text-slate-900">{item.title}</div>
                  <div className="mt-1 text-sm text-slate-400">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="text-xs text-slate-400">
            Tip: Press <kbd className="rounded border border-slate-200 bg-slate-100 px-1">Ctrl</kbd>{' '}
            + <kbd className="rounded border border-slate-200 bg-slate-100 px-1">K</kbd> for the
            command palette once signed in.
          </div>
        </div>

        {/* Right (form) panel */}
        <div className="flex items-center justify-center p-4 sm:p-6 lg:p-10">
          <div className="w-full max-w-[440px] rounded-xl border border-slate-200 bg-card p-8 shadow-xl">
            <div className="flex flex-col items-center text-center">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15 text-primary shadow-sm">
                <span className="text-lg font-bold">TP</span>
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
                Welcome back
              </h2>
              <p className="mt-1 text-sm text-slate-400">Sign in to your account</p>
            </div>

            <form
              data-testid="login-form"
              onSubmit={handleSubmit}
              className="mt-8 flex flex-col gap-5"
            >
              {state.notification && (
                <div
                  data-testid="session-notification"
                  role="status"
                  className="flex items-center gap-2 rounded-md border border-yellow-500/50 bg-yellow-500/10 px-3 py-3 text-sm text-yellow-400"
                >
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {state.notification}
                </div>
              )}

              {loginError && (
                <div
                  data-testid="login-error"
                  role="alert"
                  className="flex items-center gap-2 rounded-md border border-red-500/50 bg-red-500/10 px-3 py-3 text-sm text-red-400"
                >
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {loginError}
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-slate-600">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  data-testid="email-input"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className={cn(
                    'rounded-md border bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-300',
                    'transition-colors duration-fast focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                    errors.email ? 'border-red-500' : 'border-slate-200',
                  )}
                  placeholder="trader@test.com"
                  autoComplete="email"
                  disabled={isLoading}
                />
                {errors.email && (
                  <span data-testid="email-error" className="text-xs text-red-400">
                    {errors.email}
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-sm font-medium text-slate-600">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  data-testid="password-input"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className={cn(
                    'rounded-md border bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-300',
                    'transition-colors duration-fast focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                    errors.password ? 'border-red-500' : 'border-slate-200',
                  )}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  disabled={isLoading}
                />
                {errors.password && (
                  <span data-testid="password-error" className="text-xs text-red-400">
                    {errors.password}
                  </span>
                )}
              </div>

              <div className="flex items-center">
                <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    data-testid="remember-me-checkbox"
                    checked={rememberMe}
                    onChange={e => setRememberMe(e.target.checked)}
                    className="h-4 w-4 cursor-pointer accent-primary disabled:opacity-60 disabled:cursor-not-allowed"
                    disabled={isLoading}
                  />
                  Remember me
                </label>
              </div>

              <Button
                type="submit"
                data-testid="login-button"
                disabled={isLoading}
                className="h-11 w-full text-sm font-semibold"
              >
                {isLoading && (
                  <Loader2 data-testid="login-loading" className="h-4 w-4 animate-spin" />
                )}
                {isLoading ? 'Signing in...' : 'Sign In'}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
