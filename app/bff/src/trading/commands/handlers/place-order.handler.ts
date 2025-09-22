import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { BadRequestException, Logger } from '@nestjs/common';
import { PlaceOrderCommand } from '../place-order.command';
import { TradingService } from '../../trading.service';
import type { OrderResponse } from '../../../router-client/router-client.service';

@CommandHandler(PlaceOrderCommand)
export class PlaceOrderHandler implements ICommandHandler<PlaceOrderCommand> {
  private readonly logger = new Logger(PlaceOrderHandler.name);

  constructor(private readonly tradingService: TradingService) {}

  async execute(command: PlaceOrderCommand): Promise<OrderResponse> {
    const { userId, orderRequest } = command;

    this.validateOrder(orderRequest);
    this.logUserAction(userId, 'PLACE_ORDER', orderRequest);

    try {
      return await this.tradingService.placeOrder(orderRequest);
    } catch (error) {
      this.logger.error(`Failed to place order for user ${userId}:`, error);
      throw error;
    }
  }

  private validateOrder(order: any): void {
    if (!order.symbol || !order.side || !order.type || !order.quantity || !order.venue) {
      throw new BadRequestException('Missing required order fields');
    }

    if (order.quantity <= 0) {
      throw new BadRequestException('Order quantity must be positive');
    }

    if (order.quantity < 0.0001) {
      throw new BadRequestException('Order quantity below minimum');
    }

    if (!['BUY', 'SELL'].includes(order.side)) {
      throw new BadRequestException('Invalid order side');
    }

    if (!['MARKET', 'LIMIT'].includes(order.type)) {
      throw new BadRequestException('Invalid order type');
    }

    if (order.type === 'LIMIT' && !order.price) {
      throw new BadRequestException('LIMIT order requires price');
    }
  }

  private logUserAction(userId: string, action: string, data: any): void {
    this.logger.log(`User ${userId} action: ${action}`, data);
  }
}