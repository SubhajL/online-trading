'use client'

import { useState, useCallback, useEffect, useMemo } from 'react'
import { AppSidebar, MobileSidebar } from './AppSidebar'
import { AppTopbar } from './AppTopbar'
import { AlertsDrawer } from './AlertsDrawer'
import { HelpDrawer } from './HelpDrawer'
import { CommandPalette } from './CommandPalette'
import { cn } from '@/lib/utils'
import { alertsService } from '@/services/alerts.service'
import type { Alert } from '@/types/alerts'

type ConnectionState = 'connected' | 'reconnecting' | 'offline'

type AppShellProps = {
  children: React.ReactNode
  connectionState?: ConnectionState
  unreadAlerts?: number
  userEmail?: string
  onLogout?: () => void
  onAlertsClick?: () => void
  onHelpClick?: () => void
  onCommandPaletteClick?: () => void
}

export function AppShell({
  children,
  connectionState = 'connected',
  unreadAlerts,
  userEmail,
  onLogout,
  onAlertsClick,
  onHelpClick,
  onCommandPaletteClick,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [alerts, setAlerts] = useState<Alert[]>([])

  const toggleSidebar = useCallback(() => {
    setSidebarOpen(prev => !prev)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const result = await alertsService.getAlerts(1, 50)
        if (!cancelled) setAlerts(result.alerts ?? [])
      } catch {
        // Alerts are non-critical; ignore load failures for now.
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const derivedUnreadAlerts = useMemo(() => alerts.filter(a => !a.read).length, [alerts])
  const effectiveUnreadAlerts = unreadAlerts ?? derivedUnreadAlerts

  const openAlerts = useCallback(() => {
    setAlertsOpen(true)
    onAlertsClick?.()
  }, [onAlertsClick])

  const openHelp = useCallback(() => {
    setHelpOpen(true)
    onHelpClick?.()
  }, [onHelpClick])

  const openCommandPalette = useCallback(() => {
    setCommandPaletteOpen(true)
    onCommandPaletteClick?.()
  }, [onCommandPaletteClick])

  // Keyboard accelerators (Nielsen #7)
  useEffect(() => {
    function isTextInputTarget(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false
      const tag = target.tagName.toLowerCase()
      if (target.isContentEditable) return true
      return tag === 'input' || tag === 'textarea' || tag === 'select'
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false)
        setHelpOpen(false)
        setAlertsOpen(false)
        setMobileSidebarOpen(false)
        return
      }

      const metaOrCtrl = e.metaKey || e.ctrlKey
      if (!metaOrCtrl) return

      if (isTextInputTarget(e.target)) return

      if (e.key === 'k') {
        e.preventDefault()
        openCommandPalette()
        return
      }

      if (e.key === '/') {
        e.preventDefault()
        openHelp()
        return
      }

      if (e.key === 'b') {
        e.preventDefault()
        toggleSidebar()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [openCommandPalette, openHelp, toggleSidebar])

  const handleMarkAllAlertsRead = useCallback(async () => {
    try {
      await alertsService.markAllAsRead()
      setAlerts(prev => prev.map(a => ({ ...a, read: true })))
    } catch {
      // Non-critical.
    }
  }, [])

  return (
    <div className="flex min-h-screen flex-col bg-[#FAFBFC]" data-testid="app-shell">
      <AppTopbar
        connectionState={connectionState}
        unreadAlerts={effectiveUnreadAlerts}
        userEmail={userEmail}
        onLogout={onLogout}
        onAlertsClick={openAlerts}
        onHelpClick={openHelp}
        onCommandPaletteClick={openCommandPalette}
        onMenuClick={() => setMobileSidebarOpen(prev => !prev)}
        showMenuButton
      />

      {/* Offline banner */}
      {connectionState === 'offline' && (
        <div
          role="alert"
          className="flex items-center justify-center gap-2 bg-red-500/10 border-b border-red-500/20 px-4 py-2 text-sm text-red-400"
        >
          <span className="font-medium">Connection lost.</span>
          <span className="text-red-400/80">
            Data may be stale. Attempting to reconnect automatically.
          </span>
        </div>
      )}

      {connectionState === 'reconnecting' && (
        <div
          role="status"
          className="flex items-center justify-center gap-2 bg-yellow-500/10 border-b border-yellow-500/20 px-4 py-2 text-sm text-yellow-400"
        >
          <span className="font-medium">Reconnecting...</span>
          <span className="text-yellow-400/80">Some data may be delayed.</span>
        </div>
      )}

      <div className="flex flex-1">
        {/* Mobile sidebar (Sheet) */}
        <div className="md:hidden">
          <MobileSidebar
            connectionState={connectionState}
            open={mobileSidebarOpen}
            onOpenChange={setMobileSidebarOpen}
          />
        </div>

        {/* Desktop sidebar */}
        <AppSidebar
          isOpen={sidebarOpen}
          onToggle={toggleSidebar}
          connectionState={connectionState}
        />

        {/* Main content */}
        <main
          id="main-content"
          tabIndex={-1}
          className={cn(
            'flex-1 overflow-auto',
            'p-4 md:p-6 lg:p-8',
            'w-full min-w-0 max-w-[1400px] mx-auto',
          )}
        >
          {children}
        </main>
      </div>

      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />
      <HelpDrawer open={helpOpen} onOpenChange={setHelpOpen} />
      <AlertsDrawer
        open={alertsOpen}
        onOpenChange={setAlertsOpen}
        alerts={alerts}
        onMarkAllRead={handleMarkAllAlertsRead}
      />
    </div>
  )
}
