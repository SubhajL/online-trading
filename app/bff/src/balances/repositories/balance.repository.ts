import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { BalanceEntity } from '../entities/balance-entity';
import type { Venue } from '../dto/get-balances.dto';

@Injectable()
export class BalanceRepository {
  constructor(
    @InjectRepository(BalanceEntity)
    private readonly repository: Repository<BalanceEntity>,
  ) {}

  async findAll(venue?: Venue): Promise<BalanceEntity[]> {
    const query = this.repository
      .createQueryBuilder('balance')
      .where('balance.total > :zero', { zero: 0 })
      .orderBy('balance.venue', 'ASC')
      .addOrderBy('balance.asset', 'ASC');

    if (venue) {
      query.andWhere('balance.venue = :venue', { venue });
    }

    return query.getMany();
  }

  async findByAssetAndVenue(asset: string, venue: Venue): Promise<BalanceEntity | null> {
    return this.repository.findOne({
      where: { asset, venue },
    });
  }

  async upsert(balances: Partial<BalanceEntity>[]): Promise<void> {
    await this.repository.upsert(balances, ['asset', 'venue']);
  }

  async deleteZeroBalances(): Promise<void> {
    await this.repository
      .createQueryBuilder()
      .delete()
      .where('total = :zero', { zero: 0 })
      .execute();
  }
}
