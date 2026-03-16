'use client'

import { useState, useCallback, useEffect } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { isUiRevampEnabled } from '@/config/ui-flags'

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
  const revamp = isUiRevampEnabled()

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

  if (revamp) {
    return (
      <div className="relative flex min-h-screen flex-col overflow-hidden bg-[#101022] text-slate-100">
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(99,99,242,0.18),transparent_52%),linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:100%_100%,40px_40px,40px_40px]"
        />

        {state.notification && (
          <div className="relative z-10 border-b border-amber-500/20 bg-amber-500/10">
            <div className="mx-auto flex w-full max-w-md items-start gap-3 px-4 py-3">
              <MaterialIcon name="warning" size="md" className="mt-0.5 text-amber-400" />
              <div className="text-sm text-amber-200">{state.notification}</div>
            </div>
          </div>
        )}

        <div className="relative z-10 mx-auto flex w-full max-w-md flex-1 flex-col px-6 pb-8 pt-6">
          <header className="mb-8 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/30 bg-primary/20 text-primary">
              <MaterialIcon name="candlestick_chart" size="md" />
            </div>
            <h1 className="text-xl font-bold text-white">Online Trader</h1>
          </header>

          <div className="relative flex-1 rounded-[18px] border border-white/5 bg-[#1A1A2E] p-6 shadow-2xl">
            <div className="absolute left-0 right-0 top-0 h-1 bg-gradient-to-r from-primary via-indigo-500 to-primary" />

            <div className="mb-6">
              <h3 className="text-2xl font-bold text-white">Welcome back</h3>
              <p className="mt-1 text-sm text-slate-400">Sign in to monitor and execute safely</p>
            </div>

            <form data-testid="login-form" onSubmit={handleSubmit} className="space-y-4">
              {loginError && (
                <div
                  data-testid="login-error"
                  role="alert"
                  className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-3 text-sm text-red-300"
                >
                  <MaterialIcon name="error" size="md" className="shrink-0" />
                  {loginError}
                </div>
              )}

              <div className="space-y-1.5">
                <label htmlFor="email" className="ml-1 text-xs font-medium text-slate-300">
                  Email Access ID
                </label>
                <div className="relative">
                  <MaterialIcon
                    name="alternate_email"
                    size="md"
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
                  />
                  <input
                    id="email"
                    type="email"
                    data-testid="email-input"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className={cn(
                      'w-full rounded-xl border border-white/10 bg-[#101022] py-3 pl-10 pr-3 font-mono text-sm text-white placeholder:text-slate-600 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary',
                      errors.email && 'border-red-500',
                    )}
                    placeholder="trader@firm.com"
                    autoComplete="email"
                    disabled={isLoading}
                  />
                </div>
                {errors.email && (
                  <span data-testid="email-error" className="text-xs text-red-300">
                    {errors.email}
                  </span>
                )}
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="ml-1 text-xs font-medium text-slate-300">
                  Secure Token / Password
                </label>
                <div className="relative">
                  <MaterialIcon
                    name="lock"
                    size="md"
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
                  />
                  <input
                    id="password"
                    type="password"
                    data-testid="password-input"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className={cn(
                      'w-full rounded-xl border border-white/10 bg-[#101022] py-3 pl-10 pr-3 font-mono text-sm text-white placeholder:text-slate-600 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary',
                      errors.password && 'border-red-500',
                    )}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    disabled={isLoading}
                  />
                </div>
                {errors.password && (
                  <span data-testid="password-error" className="text-xs text-red-300">
                    {errors.password}
                  </span>
                )}
              </div>

              <div className="flex items-center pt-1">
                <label className="inline-flex items-center gap-2 text-xs text-slate-400">
                  <input
                    type="checkbox"
                    data-testid="remember-me-checkbox"
                    checked={rememberMe}
                    onChange={e => setRememberMe(e.target.checked)}
                    className="h-4 w-4 rounded border-white/20 bg-[#101022] text-primary focus:ring-primary focus:ring-offset-0"
                    disabled={isLoading}
                  />
                  Remember device
                </label>
              </div>

              <Button
                type="submit"
                data-testid="login-button"
                disabled={isLoading}
                className="mt-3 h-12 w-full rounded-xl bg-primary font-semibold text-white shadow-[0_0_15px_rgba(99,99,242,0.4)] hover:bg-primary/90"
              >
                {isLoading ? 'Authenticating...' : 'Authenticate'}
              </Button>
            </form>
          </div>

          <footer className="mt-6 flex justify-center text-xs font-mono text-slate-500">
            Security: Encrypted (TLS 1.3)
          </footer>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen bg-[#FAFBFC] dark:bg-slate-900">
      {/* Subtle background accents */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_circle_at_20%_20%,hsl(var(--primary)/0.18),transparent_55%),radial-gradient(700px_circle_at_80%_70%,hsl(var(--primary)/0.10),transparent_60%)]"
      />

      <div className="relative mx-auto grid min-h-screen w-full max-w-[1200px] grid-cols-1 lg:grid-cols-2">
        {/* Left (brand) panel */}
        <div className="hidden lg:flex flex-col justify-between p-10">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-800 bg-card/60 px-3 py-1 text-xs text-slate-600 dark:text-slate-400">
              <span className="h-2 w-2 rounded-full bg-primary" />
              Real-time monitoring • Guarded execution • Audit-friendly
            </div>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-slate-900 dark:text-white">
              Trading Platform
            </h1>
            <p className="mt-3 max-w-[46ch] text-base text-slate-600 dark:text-slate-400">
              A fast, safety-first surface for monitoring, decisions, and execution — designed for
              long sessions.
            </p>

            <div className="mt-8 grid gap-3">
              {[
                { title: 'Safety-first UI', desc: 'Guards and exposure always visible.' },
                { title: 'Keyboard accelerators', desc: 'Command palette and quick actions.' },
                { title: 'Clear states', desc: 'Loading, error, and offline are explicit.' },
              ].map(item => (
                <div
                  key={item.title}
                  className="rounded-lg border border-slate-200 dark:border-slate-800 bg-card/60 p-4"
                >
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">
                    {item.title}
                  </div>
                  <div className="mt-1 text-sm text-slate-400">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="text-xs text-slate-400">
            Tip: Press{' '}
            <kbd className="rounded border border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 px-1">
              Ctrl
            </kbd>{' '}
            +{' '}
            <kbd className="rounded border border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800 px-1">
              K
            </kbd>{' '}
            for the command palette once signed in.
          </div>
        </div>

        {/* Right (form) panel */}
        <div className="flex items-center justify-center p-4 sm:p-6 lg:p-10">
          <div className="w-full max-w-[440px] rounded-xl border border-slate-200 dark:border-slate-800 bg-card p-8 shadow-xl">
            <div className="flex flex-col items-center text-center">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15 text-primary shadow-sm">
                <span className="text-lg font-bold">TP</span>
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
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
                  <MaterialIcon name="warning" size="md" className="shrink-0" />
                  {state.notification}
                </div>
              )}

              {loginError && (
                <div
                  data-testid="login-error"
                  role="alert"
                  className="flex items-center gap-2 rounded-md border border-red-500/50 bg-red-500/10 px-3 py-3 text-sm text-red-400"
                >
                  <MaterialIcon name="error" size="md" className="shrink-0" />
                  {loginError}
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="email"
                  className="text-sm font-medium text-slate-600 dark:text-slate-400"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  data-testid="email-input"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className={cn(
                    'rounded-md border bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-white placeholder:text-slate-300 dark:placeholder:text-slate-500',
                    'transition-colors duration-fast focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                    errors.email ? 'border-red-500' : 'border-slate-200 dark:border-slate-700',
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
                <label
                  htmlFor="password"
                  className="text-sm font-medium text-slate-600 dark:text-slate-400"
                >
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
                    'rounded-md border bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-white placeholder:text-slate-300 dark:placeholder:text-slate-500',
                    'transition-colors duration-fast focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                    errors.password ? 'border-red-500' : 'border-slate-200 dark:border-slate-700',
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
                <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
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
                  <MaterialIcon name="progress_activity" size="md" className="animate-spin" />
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
