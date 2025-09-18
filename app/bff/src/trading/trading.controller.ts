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
} from '@nestjs/common';
import { TradingService } from './trading.service';
import { OrderRequest, OrderResponse } from '../router-client/router-client.service';

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

@Controller('trading')
export class TradingController {
  constructor(private readonly tradingService: TradingService) {}

  @Post('orders')
  async placeOrder(@Body() orderRequest: OrderRequest): Promise<OrderResponse> {
    return this.tradingService.placeOrder(orderRequest);
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
    @Param('orderId') orderId: string,
    @Body() cancelRequest: CancelOrderRequest,
  ): Promise<OrderResponse> {
    return this.tradingService.cancelOrder(orderId, cancelRequest.symbol, cancelRequest.venue);
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
  async setAutoTrading(@Body() request: AutoTradingRequest): Promise<AutoTradingResponse> {
    await this.tradingService.setAutoTrading(request.enabled);
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
