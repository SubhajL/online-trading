import {
  WebSocketGateway,
  SubscribeMessage,
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
import { CONTRACT_TOPICS } from '../contracts/topics';
import { AlertsService } from './alerts.service';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';
import { createWsAuthMiddleware } from '../auth/ws-auth.middleware';
import type { JwtPayload } from '../auth/interfaces/jwt-payload.interface';
import type { Alert } from './dto/alert.dto';
import type { DecisionEvent, OrderUpdateEvent } from '../trading/trading.service';

@WebSocketGateway({
  namespace: '/alerts',
  cors: {
    origin: true,
    credentials: true,
  },
})
@UseGuards(WsJwtGuard)
export class AlertsGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  private readonly logger = new Logger(AlertsGateway.name);
  private server!: Server;

  constructor(
    private readonly alertsService: AlertsService,
    private readonly eventEmitter: EventEmitter2,
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
  ) {}

  afterInit(server: Server) {
    this.server = server;
    // Populates socket.data.user before handleConnection runs; without it
    // the user check below rejected every client, authenticated or not.
    server.use(createWsAuthMiddleware(this.jwtService, this.configService));
    this.logger.log('Alerts WebSocket Gateway initialized');

    // Subscribe to alert events
    this.eventEmitter.on('alert.new', (alert: Alert) => {
      this.server.to('alerts').emit('alert.new', alert);
    });

    this.eventEmitter.on('alert.updated', (alert: Alert) => {
      this.server.to('alerts').emit('alert.updated', alert);
    });

    // Subscribe to trading events to create alerts
    this.eventEmitter.on(CONTRACT_TOPICS.decisionV1, async (decision: DecisionEvent) => {
      await this.createDecisionAlert(decision);
    });

    this.eventEmitter.on(CONTRACT_TOPICS.orderUpdateV1, async (orderUpdate: OrderUpdateEvent) => {
      await this.createOrderAlert(orderUpdate);
    });
  }

  async handleConnection(client: Socket) {
    const user = client.data.user as JwtPayload | undefined;
    if (!user?.sub) {
      this.logger.warn(`Unauthenticated alerts socket connection rejected: ${client.id}`);
      client.emit('error', { message: 'unauthorized' });
      client.disconnect(true);
      return;
    }

    this.logger.log(`Client connected to alerts: ${client.id} (user: ${user.username})`);

    // Join user-specific room for targeted alerts
    client.join(`alerts:${user.sub}`);

    // Send initial unread count
    const unreadCount = await this.alertsService.getUnreadCount();
    client.emit('connected', {
      message: 'Connected to alerts gateway',
      unreadCount: unreadCount.count,
    });
  }

  handleDisconnect(client: Socket) {
    const user = client.data.user as JwtPayload | undefined;
    this.logger.log(`Client disconnected from alerts: ${client.id}`);
    if (!user?.sub) {
      return;
    }
    client.leave(`alerts:${user.sub}`);
  }

  @SubscribeMessage('alerts:subscribe')
  subscribe(@ConnectedSocket() client: Socket) {
    client.join('alerts');
    return { event: 'subscribed', data: { message: 'Subscribed to alerts' } };
  }

  @SubscribeMessage('alerts:unsubscribe')
  unsubscribe(@ConnectedSocket() client: Socket) {
    client.leave('alerts');
    return { event: 'unsubscribed', data: { message: 'Unsubscribed from alerts' } };
  }

  @SubscribeMessage('alerts:getUnreadCount')
  async getUnreadCount() {
    return this.alertsService.getUnreadCount();
  }

  private async createDecisionAlert(decision: DecisionEvent) {
    const priority = decision.confidence >= 0.8 ? 'high' : 'medium';

    const alert = await this.alertsService.create({
      type: 'decision',
      priority,
      title: `Trading Signal: ${decision.action} ${decision.symbol}`,
      message: `Signal generated with ${Math.round(decision.confidence * 100)}% confidence`,
      data: {
        symbol: decision.symbol,
        action: decision.action,
        entry: decision.entry,
        stopLoss: decision.stopLoss,
        takeProfit: decision.takeProfit,
        confidence: decision.confidence,
      },
    });

    this.eventEmitter.emit('alert.new', alert);
  }

  private async createOrderAlert(orderUpdate: OrderUpdateEvent) {
    const priority =
      orderUpdate.status === 'FILLED'
        ? 'medium'
        : orderUpdate.status === 'REJECTED'
          ? 'high'
          : 'low';

    const alert = await this.alertsService.create({
      type: 'order',
      priority,
      title: `Order ${orderUpdate.status}: ${orderUpdate.symbol}`,
      message: `Order ${orderUpdate.orderId} has been ${orderUpdate.status}`,
      data: {
        orderId: orderUpdate.orderId,
        symbol: orderUpdate.symbol,
        status: orderUpdate.status,
        executedQty: orderUpdate.executedQty,
        executedPrice: orderUpdate.executedPrice,
      },
    });

    this.eventEmitter.emit('alert.new', alert);
  }
}
