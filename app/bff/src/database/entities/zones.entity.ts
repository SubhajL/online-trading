import { Entity, PrimaryGeneratedColumn, Column, Index } from 'typeorm';

export type ZoneType = 'order_block' | 'fair_value_gap' | 'liquidity_void';
export type ZoneSide = 'supply' | 'demand';

@Entity('zones')
@Index('idx_zones_symbol_tf', ['symbol', 'tf'])
@Index('idx_zones_status', ['is_active'])
export class Zone {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ type: 'varchar', length: 20 })
  venue!: string;

  @Column({ type: 'varchar', length: 20 })
  symbol!: string;

  @Column({ type: 'varchar', length: 5 })
  tf!: string;

  @Column({ type: 'varchar', length: 20 })
  zone_type!: ZoneType;

  @Column({ type: 'varchar', length: 10 })
  side!: ZoneSide;

  @Column({ type: 'timestamptz' })
  start_time!: Date;

  @Column({ type: 'timestamptz', nullable: true })
  end_time?: Date;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  top!: number;

  @Column({ type: 'decimal', precision: 18, scale: 8 })
  bottom!: number;

  @Column({ type: 'decimal', precision: 5, scale: 2, nullable: true })
  strength?: number;

  @Column({ type: 'boolean', default: true })
  is_active!: boolean;

  @Column({ type: 'integer', default: 0 })
  test_count!: number;

  @Column({ type: 'timestamptz', nullable: true })
  last_test_time?: Date;

  @Column({ type: 'timestamptz', nullable: true })
  broken_time?: Date;

  @Column({ type: 'timestamptz', default: () => 'CURRENT_TIMESTAMP' })
  created_at!: Date;
}
