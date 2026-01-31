import { Column, Entity, Index, PrimaryColumn } from 'typeorm';

export type ZoneType =
  | 'SUPPLY'
  | 'DEMAND'
  | 'ORDER_BLOCK_BULLISH'
  | 'ORDER_BLOCK_BEARISH'
  | 'FAIR_VALUE_GAP';

@Entity('zones')
@Index('idx_zones_symbol_tf_created', ['symbol', 'timeframe', 'created_at'])
@Index('idx_zones_active', ['symbol', 'timeframe', 'created_at'])
export class Zone {
  @PrimaryColumn({ name: 'created_at', type: 'timestamptz' })
  created_at!: Date;

  @PrimaryColumn({ name: 'zone_id', type: 'uuid' })
  zone_id!: string;

  @Column({ type: 'text' })
  venue!: string;

  @Column({ type: 'text' })
  symbol!: string;

  @Column({ name: 'timeframe', type: 'text' })
  timeframe!: string;

  @Column({ name: 'zone_type', type: 'text' })
  zone_type!: ZoneType;

  @Column({ name: 'top_price', type: 'numeric' })
  top_price!: string;

  @Column({ name: 'bottom_price', type: 'numeric' })
  bottom_price!: string;

  @Column({ name: 'strength', type: 'integer' })
  strength!: number;

  @Column({ name: 'volume_profile', type: 'numeric' })
  volume_profile!: string;

  @Column({ name: 'touches', type: 'integer' })
  touches!: number;

  @Column({ name: 'is_active', type: 'boolean' })
  is_active!: boolean;

  @Column({ name: 'tested_at', type: 'timestamptz', nullable: true })
  tested_at!: Date | null;

  @Column({ name: 'invalidated_at', type: 'timestamptz', nullable: true })
  invalidated_at!: Date | null;

  @Column({ name: 'invalidation_reason', type: 'text', nullable: true })
  invalidation_reason!: string | null;

  @Column({ name: 'origin_candle_time', type: 'timestamptz', nullable: true })
  origin_candle_time!: Date | null;

  @Column({ name: 'origin_swing_price', type: 'numeric', nullable: true })
  origin_swing_price!: string | null;

  @Column({ name: 'updated_at', type: 'timestamptz' })
  updated_at!: Date;
}
