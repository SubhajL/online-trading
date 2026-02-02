import { Column, Entity, Index, PrimaryColumn } from 'typeorm';

export type SmcEventV1Type = 'CHOCH' | 'BOS';
export type SmcDirectionV1 = 'bullish' | 'bearish';

@Entity('smc_events_v1')
@Index('idx_smc_events_v1_symbol_tf_time', ['symbol', 'timeframe', 'event_time'])
export class SmcEventV1 {
  @PrimaryColumn({ type: 'text' })
  venue!: string;

  @PrimaryColumn({ type: 'text' })
  symbol!: string;

  @PrimaryColumn({ type: 'text' })
  timeframe!: string;

  @PrimaryColumn({ name: 'event_time', type: 'timestamptz' })
  event_time!: Date;

  @PrimaryColumn({ name: 'event_type', type: 'text' })
  event_type!: SmcEventV1Type;

  @PrimaryColumn({ type: 'text' })
  direction!: SmcDirectionV1;

  @Column({ name: 'price_level', type: 'numeric' })
  price_level!: string;

  @Column({ name: 'previous_pivot_price', type: 'numeric' })
  previous_pivot_price!: string;

  @Column({ name: 'previous_pivot_time', type: 'timestamptz' })
  previous_pivot_time!: Date;

  @Column({ name: 'broken_pivot_price', type: 'numeric' })
  broken_pivot_price!: string;

  @Column({ name: 'broken_pivot_time', type: 'timestamptz' })
  broken_pivot_time!: Date;

  @Column({ type: 'text', default: '1.0.0' })
  version!: string;

  @Column({ name: 'created_at', type: 'timestamptz' })
  created_at!: Date;
}
