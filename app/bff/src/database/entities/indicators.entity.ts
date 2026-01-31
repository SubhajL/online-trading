import { Column, Entity, Index, PrimaryColumn } from 'typeorm';

@Entity('indicators')
@Index('idx_indicators_symbol_tf_time', ['symbol', 'timeframe', 'timestamp'])
export class Indicators {
  @PrimaryColumn({ type: 'text' })
  venue!: string;

  @PrimaryColumn({ type: 'text' })
  symbol!: string;

  @PrimaryColumn({ name: 'timeframe', type: 'text' })
  timeframe!: string;

  @PrimaryColumn({ type: 'timestamptz' })
  timestamp!: Date;

  @Column({ name: 'ema_9', type: 'numeric', nullable: true })
  ema_9!: string | null;

  @Column({ name: 'ema_21', type: 'numeric', nullable: true })
  ema_21!: string | null;

  @Column({ name: 'ema_50', type: 'numeric', nullable: true })
  ema_50!: string | null;

  @Column({ name: 'ema_200', type: 'numeric', nullable: true })
  ema_200!: string | null;

  @Column({ name: 'rsi_14', type: 'numeric', nullable: true })
  rsi_14!: string | null;

  @Column({ name: 'macd_line', type: 'numeric', nullable: true })
  macd_line!: string | null;

  @Column({ name: 'macd_signal', type: 'numeric', nullable: true })
  macd_signal!: string | null;

  @Column({ name: 'macd_histogram', type: 'numeric', nullable: true })
  macd_histogram!: string | null;

  @Column({ name: 'atr_14', type: 'numeric', nullable: true })
  atr_14!: string | null;

  @Column({ name: 'bb_upper', type: 'numeric', nullable: true })
  bb_upper!: string | null;

  @Column({ name: 'bb_middle', type: 'numeric', nullable: true })
  bb_middle!: string | null;

  @Column({ name: 'bb_lower', type: 'numeric', nullable: true })
  bb_lower!: string | null;

  @Column({ name: 'bb_width', type: 'numeric', nullable: true })
  bb_width!: string | null;

  @Column({ name: 'bb_percent', type: 'numeric', nullable: true })
  bb_percent!: string | null;

  @Column({ name: 'created_at', type: 'timestamptz' })
  created_at!: Date;

  @Column({ name: 'updated_at', type: 'timestamptz' })
  updated_at!: Date;
}
