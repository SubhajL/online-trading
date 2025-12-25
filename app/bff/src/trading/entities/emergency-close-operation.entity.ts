import { Entity, Column, PrimaryColumn, CreateDateColumn, UpdateDateColumn } from 'typeorm';
import type { EmergencyCloseResponse, EmergencyCloseScope } from '../dto/emergency-close.dto';

@Entity('emergency_close_operations')
export class EmergencyCloseOperationEntity {
  @PrimaryColumn({ name: 'idempotency_key', type: 'varchar', length: 128 })
  idempotencyKey!: string;

  @Column({ name: 'scope', type: 'varchar', length: 16 })
  scope!: EmergencyCloseScope;

  @Column({ name: 'stop_engine', type: 'boolean', default: false })
  stopEngine!: boolean;

  @Column({ name: 'request_signature', type: 'varchar', length: 64 })
  requestSignature!: string;

  @Column({ name: 'response', type: 'jsonb' })
  response!: EmergencyCloseResponse;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt!: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt!: Date;
}
