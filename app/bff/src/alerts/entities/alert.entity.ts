import {
  Entity,
  Column,
  PrimaryGeneratedColumn,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm';
import { AlertType, AlertPriority } from '../dto/alert.dto';

@Entity('alerts')
export class Alert {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({
    name: 'type',
    type: 'enum',
    enum: ['order', 'position', 'decision', 'smc', 'error', 'info'],
    enumName: 'alerts_type_enum',
  })
  type: AlertType;

  @Column({
    name: 'priority',
    type: 'enum',
    enum: ['low', 'medium', 'high', 'critical'],
    enumName: 'alerts_priority_enum',
  })
  priority: AlertPriority;

  @Column()
  title: string;

  @Column('text')
  message: string;

  @Column('jsonb', { nullable: true })
  data?: Record<string, unknown>;

  @Column({ default: false })
  read: boolean;

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date;
}
