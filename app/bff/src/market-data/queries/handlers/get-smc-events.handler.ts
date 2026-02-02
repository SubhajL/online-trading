import { IQueryHandler, QueryHandler } from '@nestjs/cqrs';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEventV1 } from '../../../database/entities/smc-events-v1.entity';
import type { SmcEventsV1 } from '@/contracts/gen/index';

@QueryHandler(GetSmcEventsQuery)
export class GetSmcEventsHandler implements IQueryHandler<GetSmcEventsQuery> {
  constructor(
    @InjectRepository(SmcEventV1)
    private readonly smcEventV1Repository: Repository<SmcEventV1>,
  ) {}

  async execute(query: GetSmcEventsQuery): Promise<SmcEventsV1[]> {
    const { symbol, tf, eventTypes, startTime, endTime, limit = 100 } = query;

    const queryBuilder = this.smcEventV1Repository
      .createQueryBuilder('ev')
      .where('ev.symbol = :symbol AND ev.timeframe = :timeframe', {
        symbol,
        timeframe: tf,
      });

    if (eventTypes && eventTypes.length > 0) {
      const normalized = eventTypes.map((t) => String(t).toUpperCase());
      queryBuilder.andWhere('ev.event_type IN (:...eventTypes)', { eventTypes: normalized });
    }

    if (startTime) {
      queryBuilder.andWhere('ev.event_time >= :startTime', { startTime });
    }

    if (endTime) {
      queryBuilder.andWhere('ev.event_time <= :endTime', { endTime });
    }

    const rows = await queryBuilder.orderBy('ev.event_time', 'DESC').limit(limit).getMany();
    return rows.map(toContractShape);
  }
}

function toContractShape(row: SmcEventV1): SmcEventsV1 {
  return {
    version: row.version,
    venue: row.venue,
    symbol: row.symbol,
    timeframe: row.timeframe,
    event_time: row.event_time.toISOString(),
    event_type: row.event_type === 'CHOCH' ? 'choch' : 'bos',
    direction: row.direction,
    price_level: row.price_level,
    previous_pivot_price: row.previous_pivot_price,
    previous_pivot_time: row.previous_pivot_time.toISOString(),
    broken_pivot_price: row.broken_pivot_price,
    broken_pivot_time: row.broken_pivot_time.toISOString(),
  };
}
