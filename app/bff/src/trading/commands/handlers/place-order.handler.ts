import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { BadRequestException, Logger } from '@nestjs/common';
import { PlaceOrderCommand } from '../place-order.command';
import { TradingService } from '../../trading.service';
import type { OrderRequest, OrderResponse } from '../../../router-client/router-client.service';
import { createRouterPlacementIdentity } from '../../placement-identity';

@CommandHandler(PlaceOrderCommand)
export class PlaceOrderHandler implements ICommandHandler<PlaceOrderCommand> {
  private readonly logger = new Logger(PlaceOrderHandler.name);

  constructor(private readonly tradingService: TradingService) {}

  async execute(command: PlaceOrderCommand): Promise<OrderResponse> {
    const { userId, orderRequest, idempotencyKey } = command;

    this.validateOrder(orderRequest);
    this.logUserAction(userId, 'PLACE_ORDER', orderRequest);

    try {
      const identity = createRouterPlacementIdentity(userId, idempotencyKey, 1);
      return await this.tradingService.placeOrder(orderRequest, identity);
    } catch (error) {
      this.logger.error(`Failed to place order for user ${userId}:`, error);
      throw error;
    }
  }

  private validateOrder(order: OrderRequest): void {
    if (
      !order.symbol ||
      !order.side ||
      !order.type ||
      !order.quantity ||
      !order.venue ||
      !order.stopLossPrice ||
      !order.takeProfitPrice
    ) {
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

    if (order.stopLossPrice <= 0) {
      throw new BadRequestException('Stop loss must be positive');
    }

    if (order.takeProfitPrice <= 0) {
      throw new BadRequestException('Take profit must be positive');
    }
  }

  private logUserAction(userId: string, action: string, data: OrderRequest): void {
    this.logger.log(`User ${userId} action: ${action}`, data);
  }
}
