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
import { Server, Socket } from 'socket.io';
import { EngineClientService } from '../engine-client/engine-client.service';
import { ConfigService } from '@nestjs/config';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';
import type { JwtPayload } from '../auth/interfaces/jwt-payload.interface';

interface SubscriptionData {
  symbol: string;
  timeframe: string;
}

type CandlesV1 = {
  version: string;
  venue: string;
  symbol: string;
  timeframe: string;
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  quote_volume: string;
  trades: number;
  taker_buy_volume: string;
  taker_buy_quote_volume: string;
  is_closed: boolean;
};

type FeaturesV1 = {
  version: string;
  venue: string;
  symbol: string;
  timeframe: string;
  open_time: string;
  close_time: string;
  ema_short: number | null;
  ema_long: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  atr: string | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  volume_ma: number | null;
};

type SignalsRawV1 = {
  version: string;
  venue: string;
  symbol: string;
  timeframe: string;
  signal_id: string;
  signal_time: string;
  signal_type: 'long' | 'short';
  source: string;
  entry_price: string;
  stop_loss: string;
  take_profit_1: string | null;
  take_profit_2: string | null;
  take_profit_3: string | null;
  confidence: number;
  metadata: Record<string, any>;
};

type SmcEventsV1 = {
  version: string;
  venue: string;
  symbol: string;
  timeframe: string;
  event_time: string;
  event_type: 'choch' | 'bos';
  direction: 'bullish' | 'bearish';
  price_level: string;
  previous_pivot_price: string;
  previous_pivot_time: string;
  broken_pivot_price: string;
  broken_pivot_time: string;
};

type ZonesV1 = {
  version: string;
  venue: string;
  symbol: string;
  timeframe: string;
  zone_id: string;
  zone_type: 'order_block' | 'fair_value_gap';
  direction: 'demand' | 'supply';
  upper_bound: string;
  lower_bound: string;
  created_time: string;
  candle_count: number;
  strength: number;
  touches: number;
  is_active: boolean;
};

@WebSocketGateway({
  namespace: '/trading',
  cors: {
    origin: true,
    credentials: true,
  },
})
@UseGuards(WsJwtGuard)
export class MarketDataGateway implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect {
  private readonly logger = new Logger(MarketDataGateway.name);
  private server!: Server;

  constructor(
    private readonly engineClient: EngineClientService,
    private readonly configService: ConfigService,
  ) {}

  afterInit(server: Server) {
    this.server = server;
    this.logger.log('MarketData WebSocket Gateway initialized');

    // Subscribe to engine events
    this.engineClient.subscribe('candles.v1', (data: CandlesV1) => {
      this.handleCandlesV1(data);
    });

    this.engineClient.subscribe('features.v1', (data: FeaturesV1) => {
      this.handleFeaturesV1(data);
    });

    this.engineClient.subscribe('signals_raw.v1', (data: SignalsRawV1) => {
      this.handleSignalsRawV1(data);
    });

    this.engineClient.subscribe('smc_events.v1', (data: SmcEventsV1) => {
      this.handleSmcEventsV1(data);
    });

    this.engineClient.subscribe('zones.v1', (data: ZonesV1) => {
      this.handleZonesV1(data);
    });
  }

  handleConnection(client: Socket) {
    const user = client.data.user as JwtPayload;
    this.logger.log(`Client connected: ${client.id} (user: ${user?.username})`);
    client.emit('connected', {
      message: 'Connected to market data',
      clientId: client.id,
      user: {
        username: user?.username,
        roles: user?.roles,
      },
    });
  }

  handleDisconnect(client: Socket) {
    this.logger.log(`Client disconnected: ${client.id}`);
  }

  @SubscribeMessage('subscribe')
  async subscribeToSymbol(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: SubscriptionData,
  ) {
    try {
      if (!data.symbol || !data.timeframe) {
        client.emit('error', { message: 'Invalid subscription data' });
        return;
      }

      const room = `market:${data.symbol}:${data.timeframe}`;
      await client.join(room);

      this.logger.log(`Client ${client.id} subscribed to ${room}`);
      client.emit('subscribed', {
        symbol: data.symbol,
        timeframe: data.timeframe,
      });
    } catch (error) {
      this.logger.error(`Subscription error: ${error}`);
      client.emit('error', { message: 'Failed to subscribe' });
    }
  }

  @SubscribeMessage('unsubscribe')
  async unsubscribeFromSymbol(
    @ConnectedSocket() client: Socket,
    @MessageBody() data: SubscriptionData,
  ) {
    try {
      const room = `market:${data.symbol}:${data.timeframe}`;
      await client.leave(room);

      this.logger.log(`Client ${client.id} unsubscribed from ${room}`);
      client.emit('unsubscribed', {
        symbol: data.symbol,
        timeframe: data.timeframe,
      });
    } catch (error) {
      this.logger.error(`Unsubscription error: ${error}`);
      client.emit('error', { message: 'Failed to unsubscribe' });
    }
  }

  @SubscribeMessage('subscriptions')
  getActiveSubscriptions(@ConnectedSocket() client: Socket) {
    const subscriptions: SubscriptionData[] = [];

    for (const room of client.rooms) {
      if (room.startsWith('market:')) {
        const parts = room.split(':');
        if (parts.length === 3) {
          subscriptions.push({
            symbol: parts[1],
            timeframe: parts[2],
          });
        }
      }
    }

    return { subscriptions };
  }

  private handleCandlesV1(data: CandlesV1) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('candles.v1', data);
  }

  private handleFeaturesV1(data: FeaturesV1) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('features.v1', data);
  }

  private handleSignalsRawV1(data: SignalsRawV1) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('signals_raw.v1', data);
  }

  private handleSmcEventsV1(data: SmcEventsV1) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('smc_events.v1', data);
  }

  private handleZonesV1(data: ZonesV1) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('zones.v1', data);
  }
}
