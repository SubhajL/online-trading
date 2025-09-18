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
import { EngineClientService } from '../engine-client/engine-client.service';
import { ConfigService } from '@nestjs/config';

interface SubscriptionData {
  symbol: string;
  timeframe: string;
}

interface CandleData {
  symbol: string;
  timeframe: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  closeTime: number;
}

interface FeatureData {
  symbol: string;
  timeframe: string;
  ema20?: number;
  ema50?: number;
  rsi?: number;
  macd?: {
    macd: number;
    signal: number;
    histogram: number;
  };
  atr?: number;
  bb?: {
    upper: number;
    middle: number;
    lower: number;
  };
}

interface SignalData {
  symbol: string;
  timeframe: string;
  type: 'BUY' | 'SELL';
  entry: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  timestamp?: number;
}

@WebSocketGateway({
  namespace: '/trading',
  cors: {
    origin: true,
    credentials: true,
  },
})
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
    this.engineClient.subscribe('candles.v1', (data: CandleData) => {
      this.handleCandleData(data);
    });

    this.engineClient.subscribe('features.v1', (data: FeatureData) => {
      this.handleFeatureData(data);
    });

    this.engineClient.subscribe('signals_raw.v1', (data: SignalData) => {
      this.handleSignalData(data);
    });

    this.engineClient.subscribe('smc_events.v1', (data: any) => {
      this.handleSmcData(data);
    });

    this.engineClient.subscribe('zones.v1', (data: any) => {
      this.handleZoneData(data);
    });
  }

  handleConnection(client: Socket) {
    this.logger.log(`Client connected: ${client.id}`);
    client.emit('connected', {
      message: 'Connected to market data',
      clientId: client.id,
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

  private handleCandleData(data: CandleData) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('candle', data);
  }

  private handleFeatureData(data: FeatureData) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('features', data);
  }

  private handleSignalData(data: SignalData) {
    const room = `market:${data.symbol}:${data.timeframe}`;
    this.server.to(room).emit('signal', data);
  }

  private handleSmcData(data: any) {
    if (data.symbol && data.timeframe) {
      const room = `market:${data.symbol}:${data.timeframe}`;
      this.server.to(room).emit('smc', data);
    }
  }

  private handleZoneData(data: any) {
    if (data.symbol && data.timeframe) {
      const room = `market:${data.symbol}:${data.timeframe}`;
      this.server.to(room).emit('zones', data);
    }
  }
}
