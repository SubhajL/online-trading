'use client'

import type { Position } from '@/types'
import { formatNumber } from '@/utils/formatters'
import styles from './LogoutModal.module.css'

type LogoutModalProps = {
  positions: Position[]
  loading?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function LogoutModal({ positions, loading, onCancel, onConfirm }: LogoutModalProps) {
  const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0)
  const pnlClass = totalPnl >= 0 ? styles.positive : styles.negative

  return (
    <div className={styles.overlay}>
      <div className={styles.modal} role="dialog" aria-labelledby="logout-modal-title">
        <h2 id="logout-modal-title" className={styles.title}>
          Open Positions Warning
        </h2>

        {loading ? (
          <div className={styles.loading}>Loading positions...</div>
        ) : (
          <>
            <p className={styles.message}>
              You have <strong>{positions.length}</strong> open positions that will remain active
              after logout.
            </p>

            {positions.length > 0 && (
              <div className={styles.positionsTable}>
                <div className={styles.tableHeader}>
                  <span>Symbol</span>
                  <span>Side</span>
                  <span>Size</span>
                  <span>P&L</span>
                </div>
                {positions.map((position, idx) => (
                  <div key={`${position.symbol}-${idx}`} className={styles.tableRow}>
                    <span className={styles.symbol}>{position.symbol}</span>
                    <span className={position.side === 'BUY' ? styles.buy : styles.sell}>
                      {position.side}
                    </span>
                    <span>{position.quantity}</span>
                    <span className={position.pnl >= 0 ? styles.positive : styles.negative}>
                      {formatNumber(position.pnl, 2)}
                    </span>
                  </div>
                ))}
                <div className={styles.totalRow}>
                  <span>Total P&L:</span>
                  <span className={pnlClass}>{formatNumber(totalPnl, 2)}</span>
                </div>
              </div>
            )}
          </>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            data-testid="logout-cancel"
            className={styles.cancelButton}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="logout-confirm"
            className={styles.confirmButton}
            onClick={onConfirm}
            disabled={loading}
          >
            Confirm Logout
          </button>
        </div>
      </div>
    </div>
  )
}
