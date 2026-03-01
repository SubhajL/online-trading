import { Entity, Column, PrimaryColumn, Index, CreateDateColumn } from 'typeorm';

@Entity('balances')
@Index(['venue', 'updatedAt'])
@Index(['asset', 'updatedAt'])
@Index(['updatedAt'])
export class BalanceEntity {
  @PrimaryColumn({ name: 'asset' })
  asset: string;

  @PrimaryColumn({ name: 'venue' })
  venue: 'SPOT' | 'USD_M';

  @Column('decimal', { name: 'free', precision: 18, scale: 8 })
  free: number;

  @Column('decimal', { name: 'locked', precision: 18, scale: 8 })
  locked: number;

  @Column('decimal', { name: 'total', precision: 18, scale: 8 })
  total: number;

  @Column('decimal', { name: 'usd_value', precision: 18, scale: 8, nullable: true })
  usdValue: number | null;

  @CreateDateColumn({ name: 'updated_at' })
  updatedAt: Date;
}
