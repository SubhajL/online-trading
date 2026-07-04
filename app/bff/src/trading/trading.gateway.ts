import {
  WebSocketGateway,
  SubscribeMessage,
  MessageBody,
  ConnectedSocket,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Logger, UseGuards } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import { Server, Socket } from 'socket.io';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CommandBus } from '@nestjs/cqrs';
import { TradingService } from './trading.service';
import { OrderRequest } from '../router-client/router-client.service';
import { CONTRACT_TOPICS } from '../contracts/topics';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';
import { createWsAuthMiddleware } from '../auth/ws-auth.middleware';
import type { JwtPayload } from '../auth/interfaces/jwt-payload.interface';
import { PlaceOrderCommand } from './commands/place-order.command';
import { CancelOrderCommand } from './commands/cancel-order.command';
import { SetAutoTradingCommand } from './commands/set-auto-trading.command';

interface WebSocketResponse<T = unknown> {
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
@UseGuards(WsJwtGuard)
export class TradingGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  private readonly logger = new Logger(TradingGateway.name);
  private server!: Server;

  constructor(
    private readonly tradingService: TradingService,
    private readonly eventEmitter: EventEmitter2,
    private readonly commandBus: CommandBus,
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
  ) {}

  afterInit(server: Server) {
    this.server = server;
    // Guards never run at connection time; without handshake auth anonymous
    // sockets would join 'trading' and receive every broadcast.
    server.use(createWsAuthMiddleware(this.jwtService, this.configService));
    this.logger.log('Trading WebSocket Gateway initialized');

    // Subscribe to trading events and forward to clients
    this.eventEmitter.on(CONTRACT_TOPICS.orderUpdateV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.orderUpdateV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.orderFailedV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.orderFailedV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.positionUpdateV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.positionUpdateV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.decisionV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.decisionV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.decisionSkippedV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.decisionSkippedV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.decisionFailedV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.decisionFailedV1, data);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.autoTradingV1, (data) => {
      this.server.to('trading').emit(CONTRACT_TOPICS.autoTradingV1, data);
    });
  }

  handleConnection(client: Socket) {
    const user = client.data.user as JwtPayload;
    this.logger.log(`Client connected to trading: ${client.id} (user: ${user?.username})`);
    client.join('trading');
    client.emit('connected', {
      message: 'Connected to trading gateway',
      user: {
        username: user?.username,
        roles: user?.roles,
      },
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
      const user = client.data.user as JwtPayload;
      const command = new PlaceOrderCommand(user.sub, orderRequest);
      const result = await this.commandBus.execute(command);
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
      const user = client.data.user as JwtPayload;
      const command = new CancelOrderCommand(user.sub, data.orderId, data.symbol, data.venue);
      const result = await this.commandBus.execute(command);
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
      const user = client.data.user as JwtPayload;
      const command = new SetAutoTradingCommand(user.sub, data.enabled);
      await this.commandBus.execute(command);
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
