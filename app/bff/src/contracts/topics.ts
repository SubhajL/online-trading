export const CONTRACT_TOPICS = {
  candlesV1: 'candles.v1',
  featuresV1: 'features.v1',
  smcEventsV1: 'smc_events.v1',
  zonesV1: 'zones.v1',
  signalsRawV1: 'signals_raw.v1',
  decisionV1: 'decision.v1',
  orderUpdateV1: 'order_update.v1',
  orderFailedV1: 'order_failed.v1',
  positionUpdateV1: 'position_update.v1',
  autoTradingV1: 'auto_trading.v1',
  decisionSkippedV1: 'decision_skipped.v1',
  decisionFailedV1: 'decision_failed.v1',
} as const;

export type ContractTopic = (typeof CONTRACT_TOPICS)[keyof typeof CONTRACT_TOPICS];
