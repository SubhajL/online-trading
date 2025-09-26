import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, Index, Unique } from 'typeorm';

@Entity('alert_snapshots')
@Unique(['signalId'])
export class AlertSnapshot {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ name: 'signal_id' })
  @Index()
  signalId: string;

  @Column()
  symbol: string;

  @Column()
  timeframe: string;

  @Column({ name: 'image_path' })
  imagePath: string;

  @Column({ type: 'jsonb', default: {} })
  meta: any;

  @CreateDateColumn({ name: 'created_at' })
  @Index()
  createdAt: Date;
}
