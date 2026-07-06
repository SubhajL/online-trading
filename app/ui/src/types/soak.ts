// Read-only router soak/health status, mirroring the BFF RouterSoakStatusDto.

export type RouterReadiness = {
  ready: boolean
  // 'ready' | 'reconciling' | 'unreachable'
  status: string
  error?: string
}

export type RouterReconcileSummary = {
  bracketsSwept: number
  entriesChecked: number
  legsResolved: number
  exitLegsUpdated: number
  bracketsClosed: number
  staleReserved: number
  unrepairedLegs: number
  errors: number
}

export type RouterReconcile = {
  hasRun: boolean
  lastRunAt?: string
  summary?: RouterReconcileSummary
  unavailable?: boolean
}

export type RouterSoakStatus = {
  readiness: RouterReadiness
  reconcile: RouterReconcile
  checkedAt: string
}
