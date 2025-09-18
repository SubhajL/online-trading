import {
  WebSocketGateway,
  SubscribeMessage,
  MessageBody,
  ConnectedSocket,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Logger } from '@nestjs/common';
import { Server, Socket } from 'socket.io';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { TradingService } from './trading.service';
import { OrderRequest } from '../router-client/router-client.service';

interface WebSocketResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}

@WebSocketGateway({
  namespace: '/trading',
  cors: {
    origin: true,
    credentials: true,
  },
})
export class TradingGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  private readonly logger = new Logger(TradingGateway.name);
  private server!: Server;

  constructor(
    private readonly tradingService: TradingService,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  afterInit(server: Server) {
    this.server = server;
    this.logger.log('Trading WebSocket Gateway initialized');

    // Subscribe to trading events and forward to clients
    this.eventEmitter.on('order.placed', (data) => {
      this.server.to('trading').emit('order.placed', data);
    });

    this.eventEmitter.on('order.updated', (data) => {
      this.server.to('trading').emit('order.updated', data);
    });

    this.eventEmitter.on('order.canceled', (data) => {
      this.server.to('trading').emit('order.canceled', data);
    });

    this.eventEmitter.on('order.failed', (data) => {
      this.server.to('trading').emit('order.failed', data);
    });

    this.eventEmitter.on('position.updated', (data) => {
      this.server.to('trading').emit('position.updated', data);
    });

    this.eventEmitter.on('decision.received', (data) => {
      this.server.to('trading').emit('decision.received', data);
    });

    this.eventEmitter.on('decision.skipped', (data) => {
      this.server.to('trading').emit('decision.skipped', data);
    });

    this.eventEmitter.on('decision.failed', (data) => {
      this.server.to('trading').emit('decision.failed', data);
    });

    this.eventEmitter.on('autoTrading.changed', (data) => {
      this.server.to('trading').emit('autoTrading.changed', data);
    });
  }

  handleConnection(client: Socket) {
    this.logger.log(`Client connected to trading: ${client.id}`);
    client.join('trading');
    client.emit('connected', {
      message: 'Connected to trading gateway',
    });
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client disconnected from trading: ${client.id}`);
    client.leave('trading');
  }

  @SubscribeMessage('placeOrder')
  async placeOrder(
    @ConnectedSocket() client: Socket,
    @MessageBody() orderRequest: OrderRequest,
  ): Promise<WebSocketResponse> {
    try {
      const result = await this.tradingService.placeOrder(orderRequest);
      return { success: true, data: result };
    } catch (error) {
      this.logger.error(`Failed to place order: ${error}`);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to place order',
      };
    }
  }

  @SubscribeMessage('cancelOrder')
  async cancelOrder(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { orderId: string; symbol: string; venue: 'SPOT' | 'USD_M' },
  ): Promise<WebSocketResponse> {
    try {
      const result = await this.tradingService.cancelOrder(data.orderId, data.symbol, data.venue);
      return { success: true, data: result };
    } catch (error) {
      this.logger.error(`Failed to cancel order: ${error}`);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to cancel order',
      };
    }
  }

  @SubscribeMessage('getOrderStatus')
  async getOrderStatus(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { orderId: string; venue: 'SPOT' | 'USD_M' },
  ): Promise<WebSocketResponse> {
    try {
      const result = await this.tradingService.getOrderStatus(data.orderId, data.venue);
      return { success: true, data: result };
    } catch (error) {
      this.logger.error(`Failed to get order status: ${error}`);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to get order status',
      };
    }
  }

  @SubscribeMessage('positions')
  async getPositions() {
    return this.tradingService.getPositions();
  }

  @SubscribeMessage('activeOrders')
  async getActiveOrders() {
    return this.tradingService.getActiveOrders();
  }

  @SubscribeMessage('setAutoTrading')
  async setAutoTrading(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: { enabled: boolean },
  ): Promise<WebSocketResponse> {
    try {
      await this.tradingService.setAutoTrading(data.enabled);
      return {
        success: true,
        data: {
          enabled: data.enabled,
          message: data.enabled ? 'Auto trading enabled' : 'Auto trading disabled',
        },
      };
    } catch (error) {
      this.logger.error(`Failed to set auto trading: ${error}`);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to set auto trading',
      };
    }
  }

  @SubscribeMessage('autoTradingStatus')
  async getAutoTradingStatus(): Promise<WebSocketResponse> {
    return {
      success: true,
      data: {
        enabled: this.tradingService.isAutoTradingEnabled(),
      },
    };
  }
}
