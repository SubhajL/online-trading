import { Injectable } from '@nestjs/common';
import { Balance } from './entities/balance.entity';
import { Venue } from './dto/get-balances.dto';
import { BalanceRepository } from './repositories/balance.repository';

@Injectable()
export class BalancesService {
  constructor(private readonly balanceRepository: BalanceRepository) {}

  async getBalances(venue?: Venue): Promise<Balance[]> {
    const balanceEntities = await this.balanceRepository.findAll(venue);

    return balanceEntities.map((entity) => ({
      asset: entity.asset,
      free: Number(entity.free),
      locked: Number(entity.locked),
      total: Number(entity.total),
      venue: entity.venue,
      usdValue: entity.usdValue ? Number(entity.usdValue) : null,
    }));
  }
}
