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
  Headers,
  Logger,
} from '@nestjs/common';
import { CommandBus } from '@nestjs/cqrs';
import { TradingService } from './trading.service';
import { OrderRequest, OrderResponse } from '../router-client/router-client.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import type { AuthenticatedRequest } from '../auth/interfaces/authenticated-request.interface';
import { PlaceOrderCommand } from './commands/place-order.command';
import { CancelOrderCommand } from './commands/cancel-order.command';
import { SetAutoTradingCommand } from './commands/set-auto-trading.command';
import { EmergencyCloseDto, EmergencyCloseResponse } from './dto/emergency-close.dto';
import { EmergencyCloseService } from './emergency-close.service';

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
  private readonly logger = new Logger(TradingController.name);

  constructor(
    private readonly tradingService: TradingService,
    private readonly commandBus: CommandBus,
    private readonly emergencyCloseService: EmergencyCloseService,
  ) {}

  @Post('orders')
  async placeOrder(
    @Request() req: AuthenticatedRequest,
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
    @Request() req: AuthenticatedRequest,
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
  async getPositions() {
    return this.tradingService.getPositions();
  }

  @Get('orders')
  async getActiveOrders() {
    return this.tradingService.getActiveOrders();
  }

  @Post('auto-trading')
  @HttpCode(HttpStatus.OK)
  async setAutoTrading(
    @Request() req: AuthenticatedRequest,
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

  @Post('emergency-close')
  @HttpCode(HttpStatus.OK)
  async emergencyClose(
    @Body() dto: EmergencyCloseDto,
    @Headers('X-Idempotency-Key') idempotencyKey: string,
  ): Promise<EmergencyCloseResponse> {
    this.logger.warn(
      `Emergency close requested: scope=${dto.scope}, stopEngine=${dto.stopEngine}, idempotencyKey=${idempotencyKey}`,
    );

    return this.emergencyCloseService.execute(dto, idempotencyKey);
  }
}
