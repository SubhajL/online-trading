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
    type: 'enum',
    enum: ['order', 'position', 'decision', 'smc', 'error', 'info'],
  })
  type: AlertType;

  @Column({
    type: 'enum',
    enum: ['low', 'medium', 'high', 'critical'],
  })
  priority: AlertPriority;

  @Column()
  title: string;

  @Column('text')
  message: string;

  @Column('jsonb', { nullable: true })
  data?: any;

  @Column({ default: false })
  read: boolean;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;
}
