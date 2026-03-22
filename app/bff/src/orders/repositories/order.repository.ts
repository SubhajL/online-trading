import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { OrderEntity, OrderStatus, Venue } from '../entities/order-entity';

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

  async findByExchangeOrderId(exchangeOrderId: string): Promise<OrderEntity | null> {
    return this.repository.findOne({
      where: { exchangeOrderId },
    });
  }

  async save(order: Partial<OrderEntity>): Promise<OrderEntity> {
    return this.repository.save(order);
  }

  async update(orderId: string, updates: Partial<OrderEntity>): Promise<void> {
    await this.repository.update({ orderId }, updates);
  }
}
