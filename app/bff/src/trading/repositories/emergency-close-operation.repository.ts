import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { EmergencyCloseOperationEntity } from '../entities/emergency-close-operation.entity';

@Injectable()
export class EmergencyCloseOperationRepository {
  constructor(
    @InjectRepository(EmergencyCloseOperationEntity)
    private readonly repository: Repository<EmergencyCloseOperationEntity>,
  ) {}

  async findByIdempotencyKey(
    idempotencyKey: string,
  ): Promise<EmergencyCloseOperationEntity | null> {
    return this.repository.findOne({ where: { idempotencyKey } });
  }

  async save(operation: EmergencyCloseOperationEntity): Promise<EmergencyCloseOperationEntity> {
    return this.repository.save(operation);
  }
}
