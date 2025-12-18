import { Injectable } from '@nestjs/common';
import { GetOrdersDto } from './dto/get-orders.dto';
import { Order } from './entities/order.entity';
import { OrderRepository } from './repositories/order.repository';

@Injectable()
export class OrdersService {
  constructor(private readonly orderRepository: OrderRepository) {}

  async getOrders(filters: GetOrdersDto): Promise<Order[]> {
    const orderEntities = await this.orderRepository.findAll({
      venue: filters.venue,
      symbol: filters.symbol,
      status: filters.status,
      limit: filters.limit || 100,
    });

    return orderEntities.map((entity) => ({
      orderId: entity.orderId,
      clientOrderId: entity.clientOrderId,
      symbol: entity.symbol,
      side: entity.side,
      type: entity.type,
      status: entity.status,
      venue: entity.venue,
      price: entity.price ? Number(entity.price) : undefined,
      quantity: Number(entity.quantity),
      executedQuantity: Number(entity.filledQuantity),
      avgPrice: entity.averageFillPrice ? Number(entity.averageFillPrice) : undefined,
      fee: Number(entity.commission),
      feeAsset: entity.commissionAsset || undefined,
      createdAt: entity.createdAt.toISOString(),
      updatedAt: entity.updatedAt.toISOString(),
    }));
  }
}
