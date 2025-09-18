import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import * as net from 'net';
import { createClient, RedisClientType } from 'redis';

export interface EngineEvent {
  type: string;
  data: any;
  timestamp?: string;
}

export interface HealthCheckResult {
  status: 'up' | 'down';
  details: {
    connected: boolean;
    type: 'redis' | 'tcp';
    host?: string;
    port?: number;
    error?: string;
  };
}

@Injectable()
export class EngineClientService extends EventEmitter2 {
  private readonly logger = new Logger(EngineClientService.name);
  private readonly engineType: 'redis' | 'tcp';
  private readonly host: string;
  private readonly port: number;

  private redisClient?: RedisClientType;
  private redisSubscriber?: RedisClientType;
  private tcpClient?: net.Socket;
  private isConnected = false;

  constructor(private readonly configService: ConfigService) {
    super();
    this.engineType = this.configService.get<'redis' | 'tcp'>('engine.type')!;
    this.host = this.configService.get<string>('engine.host')!;
    this.port = this.configService.get<number>('engine.port')!;
  }

  async connect(): Promise<void> {
    this.logger.log(`Connecting to engine via ${this.engineType} at ${this.host}:${this.port}`);

    if (this.engineType === 'redis') {
      await this.connectRedis();
    } else {
      await this.connectTcp();
    }

    this.isConnected = true;
  }

  async disconnect(): Promise<void> {
    this.logger.log('Disconnecting from engine');

    if (this.engineType === 'redis') {
      await this.disconnectRedis();
    } else {
      await this.disconnectTcp();
    }

    this.isConnected = false;
  }

  subscribe(eventType: string, callback: (data: any) => void): void {
    this.on(eventType, callback);
  }

  async publish(eventType: string, data: any): Promise<void> {
    const event: EngineEvent = {
      type: eventType,
      data,
      timestamp: new Date().toISOString(),
    };

    await this.publishToEngine(event);
  }

  async checkHealth(): Promise<HealthCheckResult> {
    try {
      if (!this.isConnected) {
        return {
          status: 'down',
          details: {
            connected: false,
            type: this.engineType,
            host: this.host,
            port: this.port,
          },
        };
      }

      // Try to ping the connection
      if (this.engineType === 'redis' && this.redisClient) {
        await this.redisClient.ping();
      }

      return {
        status: 'up',
        details: {
          connected: true,
          type: this.engineType,
          host: this.host,
          port: this.port,
        },
      };
    } catch (error) {
      return {
        status: 'down',
        details: {
          connected: false,
          type: this.engineType,
          host: this.host,
          port: this.port,
          error: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  private async connectRedis(): Promise<void> {
    const url = `redis://${this.host}:${this.port}`;

    // Create client for publishing
    this.redisClient = createClient({ url });
    this.redisClient.on('error', (err) => {
      this.logger.error('Redis client error:', err);
      this.emit('error', err);
    });

    // Create separate client for subscribing
    this.redisSubscriber = this.redisClient.duplicate();
    this.redisSubscriber.on('error', (err) => {
      this.logger.error('Redis subscriber error:', err);
      this.emit('error', err);
    });

    await this.redisClient.connect();
    await this.redisSubscriber.connect();

    // Subscribe to all engine events
    await this.redisSubscriber.pSubscribe('engine:*', (message, channel) => {
      try {
        const event = JSON.parse(message);
        const eventType = channel.replace('engine:', '');
        this.emit(eventType, event.data || event);
      } catch (error) {
        this.logger.error('Failed to parse engine event:', error);
      }
    });
  }

  private async connectTcp(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.tcpClient = new net.Socket();

      this.tcpClient.connect(this.port, this.host, () => {
        this.logger.log('TCP connection established');
        resolve();
      });

      this.tcpClient.on('data', (data) => {
        try {
          const lines = data.toString().split('\n').filter(Boolean);
          for (const line of lines) {
            const event = JSON.parse(line);
            this.emit(event.type, event.data);
          }
        } catch (error) {
          this.logger.error('Failed to parse TCP data:', error);
        }
      });

      this.tcpClient.on('error', (err) => {
        this.logger.error('TCP client error:', err);
        this.emit('error', err);
        reject(err);
      });

      this.tcpClient.on('close', () => {
        this.logger.warn('TCP connection closed');
        this.isConnected = false;
        this.emit('disconnected');
      });
    });
  }

  private async disconnectRedis(): Promise<void> {
    if (this.redisSubscriber) {
      await this.redisSubscriber.quit();
      this.redisSubscriber = undefined;
    }
    if (this.redisClient) {
      await this.redisClient.quit();
      this.redisClient = undefined;
    }
  }

  private async disconnectTcp(): Promise<void> {
    if (this.tcpClient) {
      this.tcpClient.destroy();
      this.tcpClient = undefined;
    }
  }

  private async publishToEngine(event: EngineEvent): Promise<void> {
    if (!this.isConnected) {
      throw new Error('Not connected to engine');
    }

    if (this.engineType === 'redis' && this.redisClient) {
      const channel = `bff:${event.type}`;
      await this.redisClient.publish(channel, JSON.stringify(event));
    } else if (this.engineType === 'tcp' && this.tcpClient) {
      const message = JSON.stringify(event) + '\n';
      this.tcpClient.write(message);
    } else {
      throw new Error('No active connection to engine');
    }
  }
}
