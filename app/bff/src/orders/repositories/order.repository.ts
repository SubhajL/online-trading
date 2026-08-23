import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import type { QueryDeepPartialEntity } from 'typeorm/query-builder/QueryPartialEntity';
import { OrderEntity } from '../entities/order-entity';
import type { OrderStatus, Venue } from '../entities/order-entity';

export interface OrderUpdateIdentity {
  venue: Venue;
  symbol: string;
  clientOrderId: string;
  exchangeOrderId: string;
}

export interface PositionSnapshot {
  venue: Venue;
  symbol: string;
  side: 'BUY' | 'SELL' | 'LONG' | 'SHORT';
  size: string | number;
  entryPrice: string | number;
  currentPrice: string | number;
  unrealizedPnl: string | number;
  updatedAt: Date;
}

export type LockedOrderUpdate = Omit<
  Partial<OrderEntity>,
  'filledQuantity' | 'averageFillPrice'
> & {
  filledQuantity?: OrderEntity['filledQuantity'] | string;
  averageFillPrice?: OrderEntity['averageFillPrice'] | string;
};

export interface LockedOrderResult {
  order: OrderEntity;
  updated: boolean;
}

@Injectable()
export class OrderRepository {
  constructor(
    @InjectRepository(OrderEntity)
    private readonly repository: Repository<OrderEntity>,
  ) {}

  async findAll(params?: {
    venue?: Venue;
    symbol?: string;
    status?: OrderStatus;
    limit?: number;
  }): Promise<OrderEntity[]> {
    const query = this.repository.createQueryBuilder('order').orderBy('order.createdAt', 'DESC');

    if (params?.venue) {
      query.andWhere('order.venue = :venue', { venue: params.venue });
    }

    if (params?.symbol) {
      query.andWhere('order.symbol = :symbol', { symbol: params.symbol });
    }

    if (params?.status) {
      query.andWhere('order.status = :status', { status: params.status });
    }

    if (params?.limit) {
      query.limit(params.limit);
    }

    return query.getMany();
  }

  async findActiveOrders(params?: { venue?: Venue; symbol?: string }): Promise<OrderEntity[]> {
    const query = this.repository
      .createQueryBuilder('order')
      .where('order.status IN (:...statuses)', { statuses: ['NEW', 'PARTIALLY_FILLED'] })
      .orderBy('order.createdAt', 'DESC');

    if (params?.venue) {
      query.andWhere('order.venue = :venue', { venue: params.venue });
    }

    if (params?.symbol) {
      query.andWhere('order.symbol = :symbol', { symbol: params.symbol });
    }

    return query.getMany();
  }

  async findActivePositionSnapshots(params?: {
    venue?: Venue;
    symbol?: string;
  }): Promise<PositionSnapshot[]> {
    const configuredSchema = (
      this.repository.manager.connection?.options as { schema?: unknown } | undefined
    )?.schema;
    const schema =
      typeof configuredSchema === 'string' && configuredSchema.trim()
        ? configuredSchema.trim()
        : 'public';
    const quotedSchema = `"${schema.replace(/"/g, '""')}"`;
    const conditions = ['is_active = TRUE'];
    const values: Array<Venue | string> = [];

    if (params?.venue) {
      conditions.push(`venue = $${values.length + 1}`);
      values.push(params.venue);
    }

    if (params?.symbol) {
      conditions.push(`symbol = $${values.length + 1}`);
      values.push(params.symbol);
    }

    return this.repository.manager.query(
      `WITH positions AS (
        SELECT venue, symbol, side, size, entry_price, current_price,
               unrealized_pnl, updated_at, is_active
        FROM ${quotedSchema}."positions"
      )
      SELECT venue,
             symbol,
             side,
             size AS "size",
             entry_price AS "entryPrice",
             current_price AS "currentPrice",
             unrealized_pnl AS "unrealizedPnl",
             updated_at AS "updatedAt"
      FROM positions
      WHERE ${conditions.join(' AND ')}`,
      values,
    );
  }

  async findByClientOrderId(clientOrderId: string, venue: Venue): Promise<OrderEntity | null> {
    return this.repository.findOne({
      where: { clientOrderId, venue },
    });
  }

  async findByOrderId(orderId: string, venue: Venue): Promise<OrderEntity | null> {
    return this.repository.findOne({
      where: { orderId, venue },
    });
  }

  async findByExchangeOrderId(
    exchangeOrderId: string,
    venue: Venue,
    symbol: string,
  ): Promise<OrderEntity | null> {
    return this.repository.findOne({
      where: { exchangeOrderId, venue, symbol },
    });
  }

  async save(order: Partial<OrderEntity>): Promise<OrderEntity> {
    return this.repository.save(order);
  }

  async update(orderId: string, updates: Partial<OrderEntity>): Promise<void> {
    await this.repository.update({ orderId }, updates);
  }

  async withLockedOrderForUpdate(
    identity: OrderUpdateIdentity,
    reconcile: (order: OrderEntity) => LockedOrderUpdate | null,
  ): Promise<LockedOrderResult | null> {
    return this.repository.manager.transaction(async (manager) => {
      const transactionalRepository = manager.getRepository(OrderEntity);

      const findLocked = async (
        field: 'clientOrderId' | 'exchangeOrderId',
        value: string,
      ): Promise<OrderEntity | null> => {
        const query = transactionalRepository
          .createQueryBuilder('order')
          .where('order.venue = :venue', { venue: identity.venue });
        if (field === 'exchangeOrderId') {
          query.andWhere('order.symbol = :symbol', { symbol: identity.symbol });
        }
        return query
          .andWhere(`order.${field} = :value`, { value })
          .setLock('pessimistic_write')
          .getOne();
      };

      const clientOrder = identity.clientOrderId
        ? await findLocked('clientOrderId', identity.clientOrderId)
        : null;
      const exchangeOrder = identity.exchangeOrderId
        ? await findLocked('exchangeOrderId', identity.exchangeOrderId)
        : null;
      if (clientOrder && exchangeOrder && clientOrder.orderId !== exchangeOrder.orderId) {
        return null;
      }
      const lockedOrder = clientOrder ?? exchangeOrder;
      if (!lockedOrder) {
        return null;
      }

      const updates = reconcile(lockedOrder);
      if (updates === null) {
        return { order: lockedOrder, updated: false };
      }

      const queryUpdates = updates as QueryDeepPartialEntity<OrderEntity>;
      await transactionalRepository.update({ orderId: lockedOrder.orderId }, queryUpdates);
      return {
        order: { ...lockedOrder, ...updates } as OrderEntity,
        updated: true,
      };
    });
  }
}
