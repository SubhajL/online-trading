import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { EquitySampleEntity } from '../entities/equity-sample.entity';

@Injectable()
export class EquitySampleRepository {
  constructor(
    @InjectRepository(EquitySampleEntity)
    private readonly repository: Repository<EquitySampleEntity>,
  ) {}

  async findLatest(): Promise<EquitySampleEntity | null> {
    return this.repository
      .createQueryBuilder('sample')
      .orderBy('sample.timestamp', 'DESC')
      .getOne();
  }

  async findSince(since: Date, limit: number): Promise<EquitySampleEntity[]> {
    return this.repository
      .createQueryBuilder('sample')
      .where('sample.timestamp >= :since', { since })
      .orderBy('sample.timestamp', 'ASC')
      .limit(limit)
      .getMany();
  }

  async insertSample(timestamp: Date, equity: number): Promise<EquitySampleEntity> {
    const entity = this.repository.create({ timestamp, equity });
    return this.repository.save(entity);
  }
}
