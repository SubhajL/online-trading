'use client'

import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import type { ExposureSummary, EmergencyCloseScope } from '@/types/dashboard'
import './EmergencyControls.css'

type EmergencyControlsProps = {
  exposure: ExposureSummary | null
  onCloseAll: (scope: EmergencyCloseScope) => void
  isClosing?: boolean
  error?: string
}

type ModalState = 'closed' | 'close-all' | 'select-scope'

export function EmergencyControls({
  exposure,
  onCloseAll,
  isClosing = false,
  error,
}: EmergencyControlsProps) {
  const [modalState, setModalState] = useState<ModalState>('closed')
  const [selectedScope, setSelectedScope] = useState<EmergencyCloseScope>('ALL')
  const [confirmationText, setConfirmationText] = useState('')

  const closeAllBtnRef = useRef<HTMLButtonElement>(null)
  const closeSpecificBtnRef = useRef<HTMLButtonElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const lastTriggerRef = useRef<'close-all' | 'close-specific' | null>(null)

  const hasPositions = exposure && exposure.positionCount > 0
  const isConfirmValid = confirmationText === 'CLOSE ALL'

  const handleCloseAllClick = useCallback(() => {
    lastTriggerRef.current = 'close-all'
    setSelectedScope('ALL')
    setConfirmationText('')
    setModalState('close-all')
  }, [])

  const handleCloseSpecificClick = useCallback(() => {
    lastTriggerRef.current = 'close-specific'
    setConfirmationText('')
    setModalState('select-scope')
  }, [])

  const handleScopeSelect = useCallback((scope: EmergencyCloseScope) => {
    setSelectedScope(scope)
    setConfirmationText('')
    setModalState('close-all')
  }, [])

  const handleConfirm = useCallback(() => {
    if (isConfirmValid && !isClosing) {
      onCloseAll(selectedScope)
      setModalState('closed')
      setConfirmationText('')
      // Return focus to the trigger button
      if (lastTriggerRef.current === 'close-all') {
        closeAllBtnRef.current?.focus()
      } else if (lastTriggerRef.current === 'close-specific') {
        closeSpecificBtnRef.current?.focus()
      }
    }
  }, [isConfirmValid, isClosing, onCloseAll, selectedScope])

  const handleCancel = useCallback(() => {
    setModalState('closed')
    setConfirmationText('')
    // Return focus to the trigger button
    if (lastTriggerRef.current === 'close-all') {
      closeAllBtnRef.current?.focus()
    } else if (lastTriggerRef.current === 'close-specific') {
      closeSpecificBtnRef.current?.focus()
    }
  }, [])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        handleCancel()
        return
      }

      // Enter key to confirm (only in confirm modal state)
      if (e.key === 'Enter' && modalState === 'close-all' && isConfirmValid && !isClosing) {
        e.preventDefault()
        handleConfirm()
        return
      }

      // Focus trap: cycle Tab within modal
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
    [handleCancel, handleConfirm, modalState, isConfirmValid, isClosing],
  )

  // Focus management: focus input when modal opens
  useEffect(() => {
    if (modalState === 'close-all' && confirmInputRef.current) {
      confirmInputRef.current.focus()
    }
  }, [modalState])

  const formatPositionCount = (count: number) => (count === 1 ? '1 position' : `${count} positions`)

  return (
    <div className="emergency-controls">
      <div className="emergency-header">
        <h3>Emergency Controls</h3>
        {isClosing && (
          <div className="closing-indicator" data-testid="closing-spinner" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            Closing...
          </div>
        )}
      </div>

      {error && (
        <div className="emergency-error" role="alert">
          {error}
        </div>
      )}

      {exposure && exposure.positionCount === 0 && (
        <div className="no-positions-message">No open positions</div>
      )}

      <div className="emergency-buttons">
        <button
          ref={closeAllBtnRef}
          type="button"
          className="emergency-btn close-all-btn"
          onClick={handleCloseAllClick}
          disabled={!hasPositions || isClosing}
        >
          <span className="btn-icon" aria-hidden="true">
            🔴
          </span>
          <span className="btn-text">CLOSE ALL POSITIONS</span>
          {exposure && exposure.positionCount > 0 && (
            <span className="btn-count" data-testid="close-all-count">
              {formatPositionCount(exposure.positionCount)}
            </span>
          )}
        </button>

        <button
          ref={closeSpecificBtnRef}
          type="button"
          className="emergency-btn close-specific-btn"
          onClick={handleCloseSpecificClick}
          disabled={!hasPositions || isClosing}
        >
          <span className="btn-icon" aria-hidden="true">
            ⚙️
          </span>
          <span className="btn-text">Close Specific...</span>
        </button>
      </div>

      {modalState !== 'closed' && (
        <div className="emergency-modal-overlay">
          <div
            ref={modalRef}
            className="emergency-modal"
            data-testid="emergency-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="emergency-modal-title"
            onKeyDown={handleKeyDown}
          >
            {modalState === 'select-scope' ? (
              <>
                <h4 id="emergency-modal-title">Select Scope</h4>
                <div className="scope-selector" data-testid="scope-selector">
                  <button
                    type="button"
                    className={`scope-option ${selectedScope === 'SPOT' ? 'selected' : ''}`}
                    onClick={() => handleScopeSelect('SPOT')}
                    data-testid="scope-spot"
                    disabled={!exposure || exposure.spotPositionCount === 0}
                  >
                    <span className="scope-label">SPOT</span>
                    <span className="scope-count" data-testid="scope-spot-count">
                      {exposure && formatPositionCount(exposure.spotPositionCount)}
                    </span>
                  </button>

                  <button
                    type="button"
                    className={`scope-option ${selectedScope === 'FUTURES' ? 'selected' : ''}`}
                    onClick={() => handleScopeSelect('FUTURES')}
                    data-testid="scope-futures"
                    disabled={!exposure || exposure.futuresPositionCount === 0}
                  >
                    <span className="scope-label">FUTURES</span>
                    <span className="scope-count" data-testid="scope-futures-count">
                      {exposure && formatPositionCount(exposure.futuresPositionCount)}
                    </span>
                  </button>
                </div>

                <div className="modal-actions">
                  <button type="button" className="cancel-btn" onClick={handleCancel}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h4 id="emergency-modal-title">Confirm Emergency Close</h4>
                <div className="confirmation-details">
                  <p>
                    You are about to close{' '}
                    <strong>
                      {selectedScope === 'ALL'
                        ? 'all positions'
                        : `${selectedScope.toLowerCase()} positions`}
                    </strong>
                    .
                  </p>
                  <p className="confirmation-warning">This action cannot be undone.</p>
                </div>

                <div className="confirmation-input-group">
                  <label htmlFor="confirm-input">Type &quot;CLOSE ALL&quot; to confirm:</label>
                  <input
                    ref={confirmInputRef}
                    id="confirm-input"
                    type="text"
                    value={confirmationText}
                    onChange={e => setConfirmationText(e.target.value)}
                    placeholder="CLOSE ALL"
                    data-testid="confirmation-input"
                    autoComplete="off"
                    disabled={isClosing}
                  />
                </div>

                <div className="modal-actions">
                  <button type="button" className="cancel-btn" onClick={handleCancel}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="confirm-btn"
                    onClick={handleConfirm}
                    disabled={!isConfirmValid || isClosing}
                    data-testid="confirm-close-btn"
                  >
                    {isClosing ? 'Closing...' : 'Close Positions'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
