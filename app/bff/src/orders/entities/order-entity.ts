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
@Index(['clientOrderId'])
@Index(['exchangeOrderId'])
@Index(['decisionId'])
export class OrderEntity {
  @PrimaryGeneratedColumn('uuid')
  orderId: string;

  @Column({ unique: true })
  clientOrderId: string;

  @Column()
  venue: Venue;

  @Column()
  symbol: string;

  @Column()
  side: OrderSide;

  @Column()
  type: OrderType;

  @Column('decimal', { precision: 18, scale: 8 })
  quantity: number;

  @Column('decimal', { precision: 18, scale: 8, nullable: true })
  price: number | null;

  @Column('decimal', { precision: 18, scale: 8, nullable: true })
  stopPrice: number | null;

  @Column({ default: 'GTC' })
  timeInForce: TimeInForce;

  @Column()
  status: OrderStatus;

  @Column('decimal', { precision: 18, scale: 8, default: 0 })
  filledQuantity: number;

  @Column('decimal', { precision: 18, scale: 8, nullable: true })
  averageFillPrice: number | null;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;

  @Column('uuid', { nullable: true })
  decisionId: string | null;

  @Column({ nullable: true })
  exchangeOrderId: string | null;

  @Column('timestamptz', { nullable: true })
  lastUpdateTime: Date | null;

  @Column('decimal', { precision: 18, scale: 8, default: 0 })
  commission: number;

  @Column({ nullable: true })
  commissionAsset: string | null;

  @Column({ default: false })
  reduceOnly: boolean;

  @Column({ default: false })
  postOnly: boolean;

  @Column({ default: false })
  closePosition: boolean;

  @Column('decimal', { precision: 18, scale: 8, nullable: true })
  activationPrice: number | null;

  @Column('decimal', { precision: 5, scale: 2, nullable: true })
  callbackRate: number | null;

  @Column({ nullable: true })
  workingType: WorkingType | null;

  @Column({ default: false })
  priceProtect: boolean;

  @Column({ nullable: true })
  rejectReason: string | null;
}
