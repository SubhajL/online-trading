import {
  Entity,
  Column,
  PrimaryGeneratedColumn,
  CreateDateColumn,
  UpdateDateColumn,
  Index,
} from 'typeorm';

export type OrderSide = 'BUY' | 'SELL';
export type OrderType =
  | 'MARKET'
  | 'LIMIT'
  | 'STOP_LOSS'
  | 'STOP_LOSS_LIMIT'
  | 'TAKE_PROFIT'
  | 'TAKE_PROFIT_LIMIT';
export type OrderStatus =
  | 'NEW'
  | 'PARTIALLY_FILLED'
  | 'FILLED'
  | 'CANCELED'
  | 'REJECTED'
  | 'EXPIRED';
export type TimeInForce = 'GTC' | 'IOC' | 'FOK' | 'GTX';
export type WorkingType = 'MARK_PRICE' | 'CONTRACT_PRICE';
export type Venue = 'SPOT' | 'USD_M';

@Entity('orders')
@Index(['venue', 'symbol', 'createdAt'])
@Index(['symbol', 'createdAt'])
@Index(['venue', 'clientOrderId'], { unique: true })
@Index(['clientOrderId'])
@Index(['exchangeOrderId'])
@Index(['decisionId'])
export class OrderEntity {
  @PrimaryGeneratedColumn('uuid', { name: 'order_id' })
  orderId: string;

  @Column({ name: 'client_order_id' })
  clientOrderId: string;

  @Column({ name: 'venue' })
  venue: Venue;

  @Column({ name: 'symbol' })
  symbol: string;

  @Column({ name: 'side' })
  side: OrderSide;

  @Column({ name: 'type' })
  type: OrderType;

  @Column('decimal', { name: 'quantity', precision: 18, scale: 8 })
  quantity: number;

  @Column('decimal', { name: 'price', precision: 18, scale: 8, nullable: true })
  price: number | null;

  @Column('decimal', { name: 'stop_price', precision: 18, scale: 8, nullable: true })
  stopPrice: number | null;

  @Column({ name: 'time_in_force', default: 'GTC' })
  timeInForce: TimeInForce;

  @Column({ name: 'status' })
  status: OrderStatus;

  @Column('decimal', { name: 'filled_quantity', precision: 18, scale: 8, default: 0 })
  filledQuantity: number;

  @Column('decimal', { name: 'average_fill_price', precision: 18, scale: 8, nullable: true })
  averageFillPrice: number | null;

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date;

  @Column('uuid', { name: 'decision_id', nullable: true })
  decisionId: string | null;

  @Column('varchar', { name: 'exchange_order_id', nullable: true })
  exchangeOrderId: string | null;

  @Column('timestamptz', { name: 'last_update_time', nullable: true })
  lastUpdateTime: Date | null;

  @Column('decimal', { name: 'commission', precision: 18, scale: 8, default: 0 })
  commission: number;

  @Column('varchar', { name: 'commission_asset', nullable: true })
  commissionAsset: string | null;

  @Column({ name: 'reduce_only', default: false })
  reduceOnly: boolean;

  @Column({ name: 'post_only', default: false })
  postOnly: boolean;

  @Column({ name: 'close_position', default: false })
  closePosition: boolean;

  @Column('decimal', { name: 'activation_price', precision: 18, scale: 8, nullable: true })
  activationPrice: number | null;

  @Column('decimal', { name: 'callback_rate', precision: 5, scale: 2, nullable: true })
  callbackRate: number | null;

  @Column('varchar', { name: 'working_type', nullable: true })
  workingType: WorkingType | null;

  @Column({ name: 'price_protect', default: false })
  priceProtect: boolean;

  @Column('varchar', { name: 'reject_reason', nullable: true })
  rejectReason: string | null;
}
