import { IQueryHandler, QueryHandler } from '@nestjs/cqrs';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEvent } from '../../../database/entities/smc-events.entity';

@QueryHandler(GetSmcEventsQuery)
export class GetSmcEventsHandler implements IQueryHandler<GetSmcEventsQuery> {
  constructor(
    @InjectRepository(SmcEvent)
    private readonly smcEventRepository: Repository<SmcEvent>,
  ) {}

  async execute(query: GetSmcEventsQuery): Promise<SmcEvent[]> {
    const { symbol, tf, eventTypes, startTime, endTime, limit = 100 } = query;

    const queryBuilder = this.smcEventRepository
      .createQueryBuilder('smc_event')
      .where('smc_event.symbol = :symbol AND smc_event.tf = :tf', { symbol, tf });

    if (eventTypes && eventTypes.length > 0) {
      queryBuilder.andWhere('smc_event.event_type IN (:...eventTypes)', { eventTypes });
    }

    if (startTime) {
      queryBuilder.andWhere('smc_event.candle_open_time >= :startTime', { startTime });
    }

    if (endTime) {
      queryBuilder.andWhere('smc_event.candle_open_time <= :endTime', { endTime });
    }

    return queryBuilder.orderBy('smc_event.candle_open_time', 'DESC').limit(limit).getMany();
  }
}
