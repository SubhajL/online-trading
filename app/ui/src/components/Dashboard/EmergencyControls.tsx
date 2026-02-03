'use client'

import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import type {
  ExposureSummary,
  EmergencyCloseScope,
  EmergencyCloseState,
  EmergencyCloseResult,
} from '@/types/dashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle } from 'lucide-react'

const STEP_ORDER = ['CANCEL_OPEN_ORDERS', 'CLOSE_POSITIONS', 'STOP_AUTO_TRADING'] as const

type StepOrderName = (typeof STEP_ORDER)[number]

function formatStepName(name: StepOrderName): string {
  switch (name) {
    case 'CANCEL_OPEN_ORDERS':
      return 'Cancel open orders'
    case 'CLOSE_POSITIONS':
      return 'Close positions'
    case 'STOP_AUTO_TRADING':
      return 'Stop auto-trading'
  }
}

type EmergencyControlsProps = {
  exposure: ExposureSummary | null
  onEmergencyClose: (
    scope: EmergencyCloseScope,
    stopEngine: boolean,
    idempotencyKey: string,
  ) => Promise<EmergencyCloseResult>
}

type ModalState = 'closed' | 'select-scope' | 'confirming' | 'executing' | 'result'

export function EmergencyControls({ exposure, onEmergencyClose }: EmergencyControlsProps) {
  const [modalState, setModalState] = useState<ModalState>('closed')
  const [selectedScope, setSelectedScope] = useState<EmergencyCloseScope>('ALL')
  const [confirmationText, setConfirmationText] = useState('')
  const [stopEngine, setStopEngine] = useState(false)
  const [executionState, setExecutionState] = useState<EmergencyCloseState>('IDLE')
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null)
  const [result, setResult] = useState<EmergencyCloseResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const closeAllBtnRef = useRef<HTMLButtonElement>(null)
  const closeSpecificBtnRef = useRef<HTMLButtonElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const lastTriggerRef = useRef<'close-all' | 'close-specific' | null>(null)

  const hasPositions = exposure && exposure.positionCount > 0
  const isConfirmValid = confirmationText === 'CLOSE ALL'

  const runEmergencyClose = useCallback(
    async (stableKey: string) => {
      setExecutionState('EXECUTING')
      setModalState('executing')
      setError(null)
      setResult(null)
      setIdempotencyKey(stableKey)
      try {
        const response = await onEmergencyClose(selectedScope, stopEngine, stableKey)
        setResult(response)
        if (response.success) {
          setExecutionState('COMPLETED')
          setError(null)
        } else {
          const stepErrors = response.steps.flatMap(step => step.errors)
          setExecutionState('FAILED')
          setError(stepErrors.length ? stepErrors.join('; ') : 'Emergency close failed.')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
        setExecutionState('FAILED')
      } finally {
        setModalState('result')
      }
    },
    [onEmergencyClose, selectedScope, stopEngine],
  )

  const resetState = useCallback(() => {
    setModalState('closed')
    setConfirmationText('')
    setStopEngine(false)
    setExecutionState('IDLE')
    setIdempotencyKey(null)
    setResult(null)
    setError(null)
  }, [])

  const handleCloseAllClick = useCallback(() => {
    lastTriggerRef.current = 'close-all'
    setSelectedScope('ALL')
    setConfirmationText('')
    setStopEngine(false)
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setIdempotencyKey(crypto.randomUUID())
    setError(null)
    setResult(null)
  }, [])

  const handleCloseSpecificClick = useCallback(() => {
    lastTriggerRef.current = 'close-specific'
    setConfirmationText('')
    setStopEngine(false)
    setModalState('select-scope')
    setError(null)
    setResult(null)
  }, [])

  const handleScopeSelect = useCallback((scope: EmergencyCloseScope) => {
    setSelectedScope(scope)
    setConfirmationText('')
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setIdempotencyKey(crypto.randomUUID())
    setError(null)
    setResult(null)
  }, [])

  const handleConfirm = useCallback(async () => {
    if (isConfirmValid && executionState !== 'EXECUTING') {
      const stableKey = idempotencyKey ?? crypto.randomUUID()
      await runEmergencyClose(stableKey)
    }
  }, [executionState, idempotencyKey, isConfirmValid, runEmergencyClose])

  const handleCancel = useCallback(() => {
    resetState()
    if (lastTriggerRef.current === 'close-all') {
      closeAllBtnRef.current?.focus()
    } else if (lastTriggerRef.current === 'close-specific') {
      closeSpecificBtnRef.current?.focus()
    }
  }, [resetState])

  const handleRetry = useCallback(async () => {
    if (executionState === 'EXECUTING') return
    if (!result) {
      const stableKey = idempotencyKey ?? crypto.randomUUID()
      await runEmergencyClose(stableKey)
      return
    }
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setConfirmationText('')
    setError(null)
    setResult(null)
    setIdempotencyKey(crypto.randomUUID())
  }, [executionState, idempotencyKey, result, runEmergencyClose])

  const handleDone = useCallback(() => {
    resetState()
    if (lastTriggerRef.current === 'close-all') {
      closeAllBtnRef.current?.focus()
    } else if (lastTriggerRef.current === 'close-specific') {
      closeSpecificBtnRef.current?.focus()
    }
  }, [resetState])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape' && modalState !== 'executing') {
        handleCancel()
        return
      }
      if (e.key === 'Enter' && modalState === 'confirming' && isConfirmValid) {
        e.preventDefault()
        handleConfirm()
        return
      }
      if (e.key === 'Tab' && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]
        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault()
          lastElement?.focus()
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault()
          firstElement?.focus()
        }
      }
    },
    [handleCancel, handleConfirm, modalState, isConfirmValid],
  )

  useEffect(() => {
    if (modalState === 'confirming' && confirmInputRef.current) {
      confirmInputRef.current.focus()
    }
  }, [modalState])

  const formatPositionCount = (count: number) => (count === 1 ? '1 position' : `${count} positions`)

  const renderSteps = (mode: 'executing' | 'result') => {
    const stepsByName = new Map(result?.steps?.map(s => [s.name, s]))
    return (
      <div className="space-y-2 mt-3" data-testid="emergency-steps">
        <h5 className="text-xs text-slate-500 uppercase tracking-wide">Steps</h5>
        <ol className="space-y-1">
          {STEP_ORDER.map(name => {
            const step = stepsByName.get(name)
            const label = formatStepName(name)
            const status =
              mode === 'executing'
                ? 'IN_PROGRESS'
                : (step?.status ?? (executionState === 'COMPLETED' ? 'SUCCESS' : 'FAILED'))
            const statusColor =
              status === 'SUCCESS'
                ? 'bg-success/15 text-success border-success/30'
                : status === 'FAILED'
                  ? 'bg-destructive/15 text-destructive border-destructive/30'
                  : 'bg-warning/15 text-warning border-warning/30'
            return (
              <li key={name} className="flex items-center justify-between text-sm">
                <span className="text-slate-600">{label}</span>
                <Badge variant="outline" className={`text-xs ${statusColor}`} data-status={status}>
                  {status}
                </Badge>
              </li>
            )
          })}
        </ol>
      </div>
    )
  }

  const renderModalContent = () => {
    switch (modalState) {
      case 'select-scope':
        return (
          <>
            <h4 id="emergency-modal-title" className="text-lg font-semibold text-slate-900">
              Select Scope
            </h4>
            <div className="flex gap-3 mt-3" data-testid="scope-selector">
              <button
                type="button"
                className={`flex-1 p-3 rounded-md border text-sm font-medium transition-all duration-fast ${
                  selectedScope === 'SPOT'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border-subtle bg-white text-slate-600 hover:border-border-strong'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
                onClick={() => handleScopeSelect('SPOT')}
                data-testid="scope-spot"
                disabled={!exposure || exposure.spotPositionCount === 0}
              >
                <span className="block font-bold">SPOT</span>
                <span className="block text-xs mt-1 text-slate-500" data-testid="scope-spot-count">
                  {exposure && formatPositionCount(exposure.spotPositionCount)}
                </span>
              </button>
              <button
                type="button"
                className={`flex-1 p-3 rounded-md border text-sm font-medium transition-all duration-fast ${
                  selectedScope === 'FUTURES'
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border-subtle bg-white text-slate-600 hover:border-border-strong'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
                onClick={() => handleScopeSelect('FUTURES')}
                data-testid="scope-futures"
                disabled={!exposure || exposure.futuresPositionCount === 0}
              >
                <span className="block font-bold">FUTURES</span>
                <span
                  className="block text-xs mt-1 text-slate-500"
                  data-testid="scope-futures-count"
                >
                  {exposure && formatPositionCount(exposure.futuresPositionCount)}
                </span>
              </button>
            </div>
            <div className="flex justify-end mt-4">
              <button
                type="button"
                className="px-4 py-2 text-sm rounded-md bg-slate-100 text-slate-600 hover:bg-surface-hover transition-colors duration-fast"
                onClick={handleCancel}
              >
                Cancel
              </button>
            </div>
          </>
        )

      case 'confirming':
        return (
          <>
            <h4 id="emergency-modal-title" className="text-lg font-semibold text-slate-900">
              Confirm Emergency Close
            </h4>
            <div className="mt-3 space-y-2 text-sm text-slate-600">
              <p>
                You are about to close{' '}
                <strong className="text-slate-900">
                  {selectedScope === 'ALL'
                    ? 'all positions'
                    : `${selectedScope.toLowerCase()} positions`}
                </strong>
                .
              </p>
              <p className="text-danger font-medium">This action cannot be undone.</p>
            </div>
            <label className="flex items-center gap-2 mt-3 text-sm text-slate-600 cursor-pointer">
              <input
                id="stop-engine-checkbox"
                type="checkbox"
                checked={stopEngine}
                onChange={e => setStopEngine(e.target.checked)}
                data-testid="stop-engine-checkbox"
                className="rounded border-border-subtle"
              />
              Also stop auto-trading after close
            </label>
            <div className="mt-3">
              <label htmlFor="confirm-input" className="block text-sm text-slate-500 mb-1">
                Type &quot;CLOSE ALL&quot; to confirm:
              </label>
              <input
                ref={confirmInputRef}
                id="confirm-input"
                type="text"
                value={confirmationText}
                onChange={e => setConfirmationText(e.target.value)}
                placeholder="CLOSE ALL"
                data-testid="confirmation-input"
                autoComplete="off"
                disabled={executionState === 'EXECUTING'}
                className="w-full px-3 py-2 text-sm rounded-md border border-border-subtle bg-surface-input text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary disabled:opacity-50"
              />
            </div>
            <div className="flex justify-end gap-3 mt-4">
              <button
                type="button"
                className="px-4 py-2 text-sm rounded-md bg-slate-100 text-slate-600 hover:bg-surface-hover transition-colors duration-fast"
                onClick={handleCancel}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-4 py-2 text-sm rounded-md bg-destructive text-white font-medium hover:bg-destructive/90 transition-colors duration-fast disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
                onClick={handleConfirm}
                disabled={!isConfirmValid || executionState === 'EXECUTING'}
                data-testid="confirm-close-btn"
              >
                Close Positions
              </button>
            </div>
          </>
        )

      case 'executing':
        return (
          <>
            <h4 id="emergency-modal-title" className="text-lg font-semibold text-slate-900">
              Closing Positions...
            </h4>
            <div className="mt-3 space-y-2" data-testid="execution-progress">
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <p>
                  Closing{' '}
                  {selectedScope === 'ALL'
                    ? 'all positions'
                    : `${selectedScope.toLowerCase()} positions`}
                  ...
                </p>
              </div>
              {stopEngine && (
                <p className="text-xs text-slate-500">Auto-trading will be stopped after close.</p>
              )}
            </div>
            {renderSteps('executing')}
          </>
        )

      case 'result':
        if (executionState === 'COMPLETED') {
          return (
            <>
              <h4 id="emergency-modal-title" className="text-lg font-semibold text-success">
                Positions Closed
              </h4>
              <div className="mt-3 space-y-2" data-testid="result-success">
                <div className="flex items-center gap-2 text-success text-2xl" aria-hidden="true">
                  ✓
                </div>
                <p className="text-sm text-slate-600">
                  Successfully closed {result?.closedPositions ?? 0} position
                  {(result?.closedPositions ?? 0) !== 1 ? 's' : ''}.
                </p>
                {result?.autoTradingDisabled && (
                  <p className="text-xs text-slate-500">Auto-trading has been stopped.</p>
                )}
              </div>
              {renderSteps('result')}
              <div className="flex justify-end mt-4">
                <button
                  type="button"
                  className="px-4 py-2 text-sm rounded-md bg-primary text-white font-medium hover:bg-primary/90 transition-colors duration-fast active:scale-[0.98]"
                  onClick={handleDone}
                  data-testid="done-btn"
                  autoFocus
                >
                  Done
                </button>
              </div>
            </>
          )
        } else {
          return (
            <>
              <h4 id="emergency-modal-title" className="text-lg font-semibold text-destructive">
                Close Failed
              </h4>
              <div className="mt-3" data-testid="result-error">
                <div
                  className="flex items-center gap-2 text-destructive text-2xl"
                  aria-hidden="true"
                >
                  ✗
                </div>
                <p className="text-sm text-destructive mt-2">
                  {error || 'Emergency close failed.'}
                </p>
              </div>
              {renderSteps('result')}
              <div className="flex justify-end gap-3 mt-4">
                <button
                  type="button"
                  className="px-4 py-2 text-sm rounded-md bg-slate-100 text-slate-600 hover:bg-surface-hover transition-colors duration-fast"
                  onClick={handleDone}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="px-4 py-2 text-sm rounded-md bg-destructive text-white font-medium hover:bg-destructive/90 transition-colors duration-fast active:scale-[0.98]"
                  onClick={handleRetry}
                  data-testid="retry-btn"
                >
                  Retry
                </button>
              </div>
            </>
          )
        }

      default:
        return null
    }
  }

  return (
    <Card className="bg-white rounded-2xl border border-slate-100 border-t-4 border-t-red-500 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.05)] hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] transition-all duration-200">
      <CardContent className="pt-6 flex flex-col items-center text-center gap-3">
        <div className="bg-red-50 text-red-500 p-3 rounded-full">
          <AlertTriangle className="h-7 w-7" />
        </div>
        <h3 className="text-lg font-bold text-slate-900">Emergency Stop</h3>
        {exposure && exposure.positionCount === 0 && (
          <p className="text-xs text-slate-400">No open positions</p>
        )}
        {exposure && exposure.positionCount > 0 && (
          <p className="text-xs text-slate-400">
            {exposure.positionCount} open position{exposure.positionCount !== 1 ? 's' : ''}
          </p>
        )}
        {!exposure && (
          <p className="text-xs text-slate-400">Immediate liquidation of all positions.</p>
        )}

        <div className="flex flex-col gap-2 w-full mt-1">
          <button
            ref={closeAllBtnRef}
            type="button"
            className="w-full px-4 py-3 min-h-[44px] text-sm font-bold rounded-xl bg-gradient-to-r from-red-500 to-red-600 text-white hover:from-red-600 hover:to-red-700 shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] flex items-center justify-center gap-2"
            onClick={handleCloseAllClick}
            disabled={!hasPositions || executionState === 'EXECUTING'}
          >
            CLOSE ALL POSITIONS
            {exposure && exposure.positionCount > 0 && (
              <span className="text-xs opacity-80" data-testid="close-all-count">
                ({formatPositionCount(exposure.positionCount)})
              </span>
            )}
          </button>

          <button
            ref={closeSpecificBtnRef}
            type="button"
            className="w-full px-4 py-2.5 min-h-[44px] text-sm font-semibold rounded-xl border border-red-200 text-red-600 bg-white hover:bg-red-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
            onClick={handleCloseSpecificClick}
            disabled={!hasPositions || executionState === 'EXECUTING'}
          >
            Close Specific...
          </button>
        </div>

        {modalState !== 'closed' && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div
              ref={modalRef}
              className={`w-full max-w-md p-6 rounded-lg shadow-lg bg-white border ${
                executionState === 'FAILED'
                  ? 'border-destructive/30'
                  : executionState === 'COMPLETED'
                    ? 'border-success/30'
                    : 'border-border-subtle'
              }`}
              data-testid="emergency-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="emergency-modal-title"
              onKeyDown={handleKeyDown}
            >
              {renderModalContent()}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
