import { Injectable } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult, HealthCheckError } from '@nestjs/terminus';
import { WebSocketHealthGateway } from '../../websockets/websocket.gateway';

@Injectable()
export class WebSocketHealthIndicator extends HealthIndicator {
  constructor(private readonly wsGateway: WebSocketHealthGateway) {
    super();
  }

  async isHealthy(key: string): Promise<HealthIndicatorResult> {
    try {
      // Get WebSocket server stats
      const server = this.wsGateway.getServer();
      const connectedClients = server?.engine?.clientsCount || 0;
      const maxConnections = 1000; // Configuration value

      // Calculate message rate (messages per second)
      // This would need to be tracked in the gateway
      const messageRate = this.getMessageRate();

      const result = this.getStatus(key, true, {
        status: 'up',
        connections: {
          active: connectedClients,
          max: maxConnections,
        },
        message_rate: messageRate,
      });

      // Check if approaching connection limit
      const connectionPercentage = (connectedClients / maxConnections) * 100;
      if (connectionPercentage >= 90) {
        (result[key] as Record<string, unknown>).status = 'degraded';
        result[key].message = 'Approaching WebSocket connection limit';
      } else if (connectionPercentage >= 80) {
        result[key].message = 'WebSocket connections high but within limits';
      } else {
        result[key].message = 'WebSocket server healthy';
      }

      return result;
    } catch (error) {
      throw new HealthCheckError(
        'WebSocket health check failed',
        this.getStatus(key, false, {
          status: 'down',
          error: (error as Error).message,
        }),
      );
    }
  }

  private getMessageRate(): number {
    // This is a simplified implementation
    // In production, you'd track actual message rates
    return 100; // Messages per second
  }
}
