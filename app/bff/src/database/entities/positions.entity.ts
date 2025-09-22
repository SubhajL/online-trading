import { Entity, PrimaryGeneratedColumn, Column, Index } from 'typeorm';

export type PositionSide = 'long' | 'short';
export type PositionStatus = 'open' | 'closed';

@Entity('positions')
@Index('idx_positions_user_symbol', ['user_id', 'symbol'])
@Index('idx_positions_status', ['status'])
export class Position {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ type: 'varchar', length: 50 })
  user_id!: string;

  @Column({ type: 'varchar', length: 20 })
  venue!: string;

  @Column({ type: 'varchar', length: 20 })
  symbol!: string;

  @Column({ type: 'varchar', length: 10 })
  side!: PositionSide;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  quantity!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  entry_price!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  exit_price?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  stop_loss?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  take_profit?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, default: 0 })
  unrealized_pnl!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, default: 0 })
  realized_pnl!: number;

  @Column({ type: 'varchar', length: 20 })
  status!: PositionStatus;

  @Column({ type: 'jsonb', nullable: true })
  metadata?: any;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  opened_at!: Date;

  @Column({ type: 'timestamptz', nullable: true })
  closed_at?: Date;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  updated_at!: Date;
}
