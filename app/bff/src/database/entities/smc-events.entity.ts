import { Column, Entity, Index, PrimaryColumn } from 'typeorm';

export type SmcStructureType = 'HH' | 'HL' | 'LH' | 'LL' | 'EH' | 'EL';
export type SmcTrendDirection = 'bullish' | 'bearish' | 'neutral';
export type SmcEventType = 'CHOCH' | 'BOS' | 'STRUCTURE';

@Entity('smc_events')
@Index('idx_smc_events_symbol_tf_time', ['symbol', 'timeframe', 'timestamp'])
export class SmcEvent {
  @PrimaryColumn({ type: 'text' })
  venue!: string;

  @PrimaryColumn({ type: 'text' })
  symbol!: string;

  @PrimaryColumn({ name: 'timeframe', type: 'text' })
  timeframe!: string;

  @PrimaryColumn({ type: 'timestamptz' })
  timestamp!: Date;

  @PrimaryColumn({ name: 'structure_type', type: 'text' })
  structure_type!: SmcStructureType;

  @Column({ name: 'price', type: 'numeric' })
  price!: string;

  @Column({ name: 'previous_structure', type: 'text', nullable: true })
  previous_structure!: SmcStructureType | null;

  @Column({ name: 'trend_direction', type: 'text', nullable: true })
  trend_direction!: SmcTrendDirection | null;

  @Column({ name: 'event_type', type: 'text' })
  event_type!: SmcEventType;

  @Column({ name: 'break_price', type: 'numeric', nullable: true })
  break_price!: string | null;

  @Column({ name: 'volume_at_break', type: 'numeric', nullable: true })
  volume_at_break!: string | null;

  @Column({ name: 'created_at', type: 'timestamptz' })
  created_at!: Date;
}
