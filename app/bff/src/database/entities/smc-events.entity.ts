import { Entity, PrimaryGeneratedColumn, Column, Index } from 'typeorm';

export type SmcEventType = 'HH' | 'HL' | 'LH' | 'LL' | 'CHOCH' | 'BOS';
export type SmcDirection = 'bullish' | 'bearish' | 'neutral';

@Entity('smc_events')
@Index('idx_smc_events_symbol_tf_time', ['symbol', 'tf', 'candle_open_time'])
export class SmcEvent {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ type: 'varchar', length: 20 })
  venue!: string;

  @Column({ type: 'varchar', length: 20 })
  symbol!: string;

  @Column({ type: 'varchar', length: 5 })
  tf!: string;

  @Column({ type: 'timestamptz' })
  candle_open_time!: Date;

  @Column({ type: 'varchar', length: 10 })
  event_type!: SmcEventType;

  @Column({ type: 'varchar', length: 10 })
  direction!: SmcDirection;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  price!: number;

  @Column({ type: 'integer', nullable: true })
  pivot_index?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  prev_pivot_price?: number;

  @Column({ type: 'timestamptz', nullable: true })
  prev_pivot_time?: Date;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  created_at!: Date;
}
