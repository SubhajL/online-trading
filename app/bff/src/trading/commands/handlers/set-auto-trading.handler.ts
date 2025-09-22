import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { SetAutoTradingCommand } from '../set-auto-trading.command';
import { TradingService } from '../../trading.service';

@CommandHandler(SetAutoTradingCommand)
export class SetAutoTradingHandler implements ICommandHandler<SetAutoTradingCommand> {
  private readonly logger = new Logger(SetAutoTradingHandler.name);

  constructor(private readonly tradingService: TradingService) {}

  async execute(command: SetAutoTradingCommand): Promise<void> {
    const { userId, enabled } = command;

    this.logger.log(`User ${userId} setting auto-trading to ${enabled}`);

    try {
      await this.tradingService.setAutoTrading(enabled);
    } catch (error) {
      this.logger.error(`Failed to set auto-trading for user ${userId}:`, error);
      throw error;
    }
  }
}
