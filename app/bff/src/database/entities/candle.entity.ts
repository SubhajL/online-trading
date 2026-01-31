import { Column, Entity, Index, PrimaryColumn } from 'typeorm';

@Entity('candles')
@Index('idx_candles_symbol_tf_time', ['symbol', 'timeframe', 'open_time'])
export class Candle {
  @PrimaryColumn({ type: 'text' })
  venue!: string;

  @PrimaryColumn({ type: 'text' })
  symbol!: string;

  @PrimaryColumn({ name: 'timeframe', type: 'text' })
  timeframe!: string;

  @PrimaryColumn({ name: 'open_time', type: 'timestamp' })
  open_time!: Date;

  @Column({ name: 'close_time', type: 'timestamp' })
  close_time!: Date;

  @Column({ name: 'open_price', type: 'numeric' })
  open_price!: string;

  @Column({ name: 'high_price', type: 'numeric' })
  high_price!: string;

  @Column({ name: 'low_price', type: 'numeric' })
  low_price!: string;

  @Column({ name: 'close_price', type: 'numeric' })
  close_price!: string;

  @Column({ type: 'numeric' })
  volume!: string;

  @Column({ name: 'quote_volume', type: 'numeric' })
  quote_volume!: string;

  @Column({ type: 'integer' })
  trades!: number;

  @Column({ name: 'taker_buy_base_volume', type: 'numeric' })
  taker_buy_base_volume!: string;

  @Column({ name: 'taker_buy_quote_volume', type: 'numeric' })
  taker_buy_quote_volume!: string;

  @Column({ name: 'created_at', type: 'timestamptz' })
  created_at!: Date;

  @Column({ name: 'updated_at', type: 'timestamptz' })
  updated_at!: Date;
}
