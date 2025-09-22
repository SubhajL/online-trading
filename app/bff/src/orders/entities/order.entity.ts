export type OrderStatus =
  | 'NEW'
  | 'FILLED'
  | 'PARTIALLY_FILLED'
  | 'CANCELED'
  | 'REJECTED'
  | 'EXPIRED';
export type OrderSide = 'BUY' | 'SELL';
export type OrderType =
  | 'MARKET'
  | 'LIMIT'
  | 'STOP_LOSS'
  | 'STOP_LOSS_LIMIT'
  | 'TAKE_PROFIT'
  | 'TAKE_PROFIT_LIMIT';
export type Venue = 'SPOT' | 'USD_M';

export interface Order {
  id: string;
  clientOrderId: string;
  symbol: string;
  side: OrderSide;
  type: OrderType;
  status: OrderStatus;
  venue: Venue;
  price?: number;
  quantity: number;
  executedQty?: number;
  fee?: number;
  feeAsset?: string;
  createdAt: string;
  updatedAt: string;
}
