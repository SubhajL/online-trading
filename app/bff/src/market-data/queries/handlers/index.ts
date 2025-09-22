export * from './get-candles.handler';
export * from './get-indicators.handler';
export * from './get-smc-events.handler';

import { GetCandlesHandler } from './get-candles.handler';
import { GetIndicatorsHandler } from './get-indicators.handler';
import { GetSmcEventsHandler } from './get-smc-events.handler';

export const QueryHandlers = [GetCandlesHandler, GetIndicatorsHandler, GetSmcEventsHandler];
