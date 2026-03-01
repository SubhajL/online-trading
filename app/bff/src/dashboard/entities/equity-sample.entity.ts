import { Entity, Column, PrimaryGeneratedColumn, Index, CreateDateColumn } from 'typeorm';

@Entity('equity_samples')
@Index(['timestamp'])
export class EquitySampleEntity {
  @PrimaryGeneratedColumn('uuid', { name: 'id' })
  id!: string;

  @Column({ name: 'timestamp', type: 'timestamptz' })
  timestamp!: Date;

  @Column({ name: 'source_timestamp', type: 'timestamptz', nullable: true })
  sourceTimestamp!: Date | null;

  @Column('decimal', { name: 'equity', precision: 18, scale: 8 })
  equity!: number;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt!: Date;
}
