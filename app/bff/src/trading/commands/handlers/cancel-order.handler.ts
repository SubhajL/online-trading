import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { CancelOrderCommand } from '../cancel-order.command';
import { TradingService } from '../../trading.service';
import type { OrderResponse } from '../../../router-client/router-client.service';

@CommandHandler(CancelOrderCommand)
export class CancelOrderHandler implements ICommandHandler<CancelOrderCommand> {
  private readonly logger = new Logger(CancelOrderHandler.name);

  constructor(private readonly tradingService: TradingService) {}

  async execute(command: CancelOrderCommand): Promise<OrderResponse> {
    const { userId, orderId, symbol, venue } = command;

    this.logger.log(`User ${userId} canceling order ${orderId}`);

    try {
      return await this.tradingService.cancelOrder(orderId, symbol, venue);
    } catch (error) {
      this.logger.error(`Failed to cancel order ${orderId} for user ${userId}:`, error);
      throw error;
    }
  }
}