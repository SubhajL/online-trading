import { Entity, Column, PrimaryColumn, Index, CreateDateColumn } from 'typeorm';

@Entity('balances')
@Index(['venue', 'updatedAt'])
@Index(['asset', 'updatedAt'])
@Index(['updatedAt'])
export class BalanceEntity {
  @PrimaryColumn()
  asset: string;

  @PrimaryColumn()
  venue: 'SPOT' | 'USD_M';

  @Column('decimal', { precision: 18, scale: 8 })
  free: number;

  @Column('decimal', { precision: 18, scale: 8 })
  locked: number;

  @Column('decimal', { precision: 18, scale: 8 })
  total: number;

  @Column('decimal', { precision: 18, scale: 8, nullable: true })
  usdValue: number | null;

  @CreateDateColumn({ name: 'updated_at' })
  updatedAt: Date;
}
