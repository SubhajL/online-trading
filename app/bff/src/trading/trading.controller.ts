import {
  Controller,
  Post,
  Get,
  Delete,
  Body,
  Param,
  Query,
  HttpCode,
  HttpStatus,
  UseGuards,
  Request,
} from '@nestjs/common';
import { CommandBus } from '@nestjs/cqrs';
import { TradingService } from './trading.service';
import { OrderRequest, OrderResponse } from '../router-client/router-client.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { Public } from '../auth/decorators/public.decorator';
import { PlaceOrderCommand } from './commands/place-order.command';
import { CancelOrderCommand } from './commands/cancel-order.command';
import { SetAutoTradingCommand } from './commands/set-auto-trading.command';

interface CancelOrderRequest {
  symbol: string;
  venue: 'SPOT' | 'USD_M';
}

interface AutoTradingRequest {
  enabled: boolean;
}

interface AutoTradingResponse {
  enabled: boolean;
  message: string;
}

@UseGuards(JwtAuthGuard)
@Controller('trading')
export class TradingController {
  constructor(
    private readonly tradingService: TradingService,
    private readonly commandBus: CommandBus,
  ) {}

  @Post('orders')
  async placeOrder(
    @Request() req: any,
    @Body() orderRequest: OrderRequest,
  ): Promise<OrderResponse> {
    const command = new PlaceOrderCommand(req.user.sub, orderRequest);
    return this.commandBus.execute(command);
  }

  @Get('orders/:orderId')
  async getOrderStatus(
    @Param('orderId') orderId: string,
    @Query('venue') venue: 'SPOT' | 'USD_M',
  ): Promise<OrderResponse> {
    return this.tradingService.getOrderStatus(orderId, venue);
  }

  @Delete('orders/:orderId')
  async cancelOrder(
    @Request() req: any,
    @Param('orderId') orderId: string,
    @Body() cancelRequest: CancelOrderRequest,
  ): Promise<OrderResponse> {
    const command = new CancelOrderCommand(
      req.user.sub,
      orderId,
      cancelRequest.symbol,
      cancelRequest.venue,
    );
    return this.commandBus.execute(command);
  }

  @Get('positions')
  @Public()
  async getPositions() {
    return this.tradingService.getPositions();
  }

  @Get('orders')
  @Public()
  async getActiveOrders() {
    return this.tradingService.getActiveOrders();
  }

  @Post('auto-trading')
  @HttpCode(HttpStatus.OK)
  async setAutoTrading(
    @Request() req: any,
    @Body() request: AutoTradingRequest,
  ): Promise<AutoTradingResponse> {
    const command = new SetAutoTradingCommand(req.user.sub, request.enabled);
    await this.commandBus.execute(command);
    return {
      enabled: request.enabled,
      message: request.enabled ? 'Auto trading enabled' : 'Auto trading disabled',
    };
  }

  @Get('auto-trading')
  getAutoTradingStatus(): { enabled: boolean } {
    return {
      enabled: this.tradingService.isAutoTradingEnabled(),
    };
  }
}
