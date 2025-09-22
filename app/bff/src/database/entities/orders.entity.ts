import { Entity, PrimaryGeneratedColumn, Column, Index } from 'typeorm';

export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_market';
export type OrderStatus = 'new' | 'filled' | 'partially_filled' | 'cancelled' | 'rejected';

@Entity('orders')
@Index('idx_orders_user_symbol', ['user_id', 'symbol'])
@Index('idx_orders_status', ['status'])
export class Order {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ type: 'varchar', length: 50, nullable: true })
  exchange_order_id?: string;

  @Column({ type: 'varchar', length: 50 })
  client_order_id!: string;

  @Column({ type: 'varchar', length: 50 })
  user_id!: string;

  @Column({ type: 'varchar', length: 20 })
  venue!: string;

  @Column({ type: 'varchar', length: 20 })
  symbol!: string;

  @Column({ type: 'varchar', length: 10 })
  side!: OrderSide;

  @Column({ type: 'varchar', length: 20 })
  type!: OrderType;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  quantity!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  price?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  stop_price?: number;

  @Column({ type: 'varchar', length: 20 })
  status!: OrderStatus;

  @Column({ type: 'decimal', precision: 18, scale: 8, default: 0 })
  filled_quantity!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  avg_fill_price?: number;

  @Column({ type: 'text', nullable: true })
  reject_reason?: string;

  @Column({ type: 'jsonb', nullable: true })
  metadata?: any;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  created_at!: Date;

  @Column({ type: 'timestamptz', nullable: true })
  filled_at?: Date;

  @Column({ type: 'timestamptz', nullable: true })
  cancelled_at?: Date;
}
