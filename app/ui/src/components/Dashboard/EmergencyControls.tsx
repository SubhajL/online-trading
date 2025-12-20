'use client'

import { useState, useCallback } from 'react'
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

  const hasPositions = exposure && exposure.positionCount > 0
  const isConfirmValid = confirmationText === 'CLOSE ALL'

  const handleCloseAllClick = useCallback(() => {
    setSelectedScope('ALL')
    setConfirmationText('')
    setModalState('close-all')
  }, [])

  const handleCloseSpecificClick = useCallback(() => {
    setConfirmationText('')
    setModalState('select-scope')
  }, [])

  const handleScopeSelect = useCallback((scope: EmergencyCloseScope) => {
    setSelectedScope(scope)
    setConfirmationText('')
    setModalState('close-all')
  }, [])

  const handleConfirm = useCallback(() => {
    if (isConfirmValid) {
      onCloseAll(selectedScope)
      setModalState('closed')
      setConfirmationText('')
    }
  }, [isConfirmValid, onCloseAll, selectedScope])

  const handleCancel = useCallback(() => {
    setModalState('closed')
    setConfirmationText('')
  }, [])

  const formatPositionCount = (count: number) => (count === 1 ? '1 position' : `${count} positions`)

  return (
    <div className="emergency-controls">
      <div className="emergency-header">
        <h3>Emergency Controls</h3>
        {isClosing && (
          <div className="closing-indicator" data-testid="closing-spinner">
            <span className="spinner" />
            Closing...
          </div>
        )}
      </div>

      {error && <div className="emergency-error">{error}</div>}

      {exposure && exposure.positionCount === 0 && (
        <div className="no-positions-message">No open positions</div>
      )}

      <div className="emergency-buttons">
        <button
          type="button"
          className="emergency-btn close-all-btn"
          onClick={handleCloseAllClick}
          disabled={!hasPositions || isClosing}
        >
          <span className="btn-icon">🔴</span>
          <span className="btn-text">CLOSE ALL POSITIONS</span>
          {exposure && exposure.positionCount > 0 && (
            <span className="btn-count" data-testid="close-all-count">
              {formatPositionCount(exposure.positionCount)}
            </span>
          )}
        </button>

        <button
          type="button"
          className="emergency-btn close-specific-btn"
          onClick={handleCloseSpecificClick}
          disabled={!hasPositions || isClosing}
        >
          <span className="btn-icon">⚙️</span>
          <span className="btn-text">Close Specific...</span>
        </button>
      </div>

      {modalState !== 'closed' && (
        <div className="emergency-modal-overlay">
          <div className="emergency-modal" data-testid="emergency-modal">
            {modalState === 'select-scope' ? (
              <>
                <h4>Select Scope</h4>
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
                <h4>Confirm Emergency Close</h4>
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
                    id="confirm-input"
                    type="text"
                    value={confirmationText}
                    onChange={e => setConfirmationText(e.target.value)}
                    placeholder="CLOSE ALL"
                    data-testid="confirmation-input"
                    autoComplete="off"
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
                    disabled={!isConfirmValid}
                    data-testid="confirm-close-btn"
                  >
                    Close Positions
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
