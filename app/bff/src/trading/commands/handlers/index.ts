import { PlaceOrderHandler } from './place-order.handler';
import { CancelOrderHandler } from './cancel-order.handler';
import { SetAutoTradingHandler } from './set-auto-trading.handler';

export const CommandHandlers = [
  PlaceOrderHandler,
  CancelOrderHandler,
  SetAutoTradingHandler,
];