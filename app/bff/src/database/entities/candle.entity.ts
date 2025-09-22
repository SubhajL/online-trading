import { Entity, PrimaryColumn, Column, Index } from 'typeorm';

@Entity('candles')
@Index('idx_candles_symbol_tf_time', ['symbol', 'tf', 'open_time'])
export class Candle {
  @PrimaryColumn({ type: 'varchar', length: 20 })
  venue!: string;

  @PrimaryColumn({ type: 'varchar', length: 20 })
  symbol!: string;

  @PrimaryColumn({ type: 'varchar', length: 5 })
  tf!: string;

  @PrimaryColumn({ type: 'timestamptz' })
  open_time!: Date;

  @Column({ type: 'timestamptz' })
  close_time!: Date;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  open!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  high!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  low!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  close!: number;

  @Column({ type: 'decimal', precision: 28, scale: 8 })
  volume!: number;

  @Column({ type: 'bigint' })
  trades!: number;

  @Column({ type: 'boolean', default: false })
  is_final!: boolean;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  created_at!: Date;
}
