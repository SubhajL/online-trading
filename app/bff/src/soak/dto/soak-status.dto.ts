// Read-only view of the router's deferred-legs + reconciler state, surfaced
// for the soak/health observability panel.

export class RouterReadinessDto {
  ready!: boolean;
  // 'ready' | 'reconciling' | 'unreachable'
  status!: string;
  error?: string;
}

// Mirrors the router's orders.ReconcileSummary (startup_reconciler.go).
export class RouterReconcileSummaryDto {
  bracketsSwept!: number;
  entriesChecked!: number;
  legsResolved!: number;
  exitLegsUpdated!: number;
  bracketsClosed!: number;
  staleReserved!: number;
  unrepairedLegs!: number;
  errors!: number;
}

export class RouterReconcileDto {
  hasRun!: boolean;
  lastRunAt?: string;
  summary?: RouterReconcileSummaryDto;
  // True when the router's reconcile status could not be fetched.
  unavailable?: boolean;
}

export class RouterSoakStatusDto {
  readiness!: RouterReadinessDto;
  reconcile!: RouterReconcileDto;
  checkedAt!: string;
}
