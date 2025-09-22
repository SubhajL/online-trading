import { Entity, PrimaryColumn, Column, Index } from 'typeorm';

@Entity('indicators')
@Index('idx_indicators_symbol_tf_time', ['symbol', 'tf', 'candle_open_time'])
export class Indicators {
  @PrimaryColumn({ type: 'varchar', length: 20 })
  venue!: string;

  @PrimaryColumn({ type: 'varchar', length: 20 })
  symbol!: string;

  @PrimaryColumn({ type: 'varchar', length: 5 })
  tf!: string;

  @PrimaryColumn({ type: 'timestamptz' })
  candle_open_time!: Date;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  ema_9?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  ema_21?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  ema_50?: number;

  @Column({ type: 'decimal', precision: 10, scale: 2, nullable: true })
  rsi_14?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  macd_line?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  macd_signal?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  macd_histogram?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  atr_14?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  bb_upper?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  bb_middle?: number;

  @Column({ type: 'decimal', precision: 18, scale: 8, nullable: true })
  bb_lower?: number;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  created_at!: Date;
}
