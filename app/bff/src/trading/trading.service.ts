import { Injectable, Logger } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { EngineClientService } from '../engine-client/engine-client.service';
import {
  RouterClientService,
  OrderRequest,
  OrderResponse,
} from '../router-client/router-client.service';

export interface Position {
  symbol: string;
  side: 'LONG' | 'SHORT';
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPercent: number;
  venue: 'SPOT' | 'USD_M';
  timestamp: number;
}

export interface DecisionEvent {
  symbol: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  venue: 'SPOT' | 'USD_M';
  type: 'MARKET' | 'LIMIT';
  price?: number;
  confidence: number;
  timestamp?: number;
}

export interface OrderUpdateEvent {
  orderId: string;
  symbol: string;
  status: string;
  executedQty?: number;
  executedPrice?: number;
  timestamp?: number;
}

@Injectable()
export class TradingService {
  private readonly logger = new Logger(TradingService.name);
  private readonly positions = new Map<string, Position>();
  private readonly activeOrders = new Map<string, OrderResponse>();
  private autoTrading = false;

  constructor(
    private readonly engineClient: EngineClientService,
    private readonly routerClient: RouterClientService,
    private readonly eventEmitter: EventEmitter2,
  ) {
    this.subscribeToEngineEvents();
  }

  private subscribeToEngineEvents() {
    // Subscribe to decision events from engine
    this.engineClient.subscribe('decision.v1', (event: DecisionEvent) => {
      this.eventEmitter.emit('decision.received', event);
      this.handleDecisionEvent(event);
    });

    // Subscribe to order update events
    this.engineClient.subscribe('order_update.v1', (event: OrderUpdateEvent) => {
      this.eventEmitter.emit('order.updated', event);
      this.handleOrderUpdate(event);
    });
  }

  async placeOrder(request: OrderRequest): Promise<OrderResponse> {
    try {
      this.logger.log(`Placing order: ${JSON.stringify(request)}`);

      const response = await this.routerClient.placeOrder(request);

      // Track the active order
      this.activeOrders.set(response.orderId, response);

      // Emit order placed event
      this.eventEmitter.emit('order.placed', response);

      return response;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      this.logger.error(`Failed to place order: ${errorMessage}`);

      this.eventEmitter.emit('order.failed', {
        request,
        error: errorMessage,
      });

      throw error;
    }
  }

  async getOrderStatus(orderId: string, venue: 'SPOT' | 'USD_M'): Promise<OrderResponse> {
    return this.routerClient.getOrderStatus(orderId, venue);
  }

  async cancelOrder(
    orderId: string,
    symbol: string,
    venue: 'SPOT' | 'USD_M',
  ): Promise<OrderResponse> {
    const response = await this.routerClient.cancelOrder(orderId, symbol, venue);

    // Remove from active orders
    this.activeOrders.delete(orderId);

    // Emit order canceled event
    this.eventEmitter.emit('order.canceled', response);

    return response;
  }

  async getPositions(): Promise<Position[]> {
    return Array.from(this.positions.values());
  }

  async getActiveOrders(): Promise<OrderResponse[]> {
    return Array.from(this.activeOrders.values());
  }

  async setAutoTrading(enabled: boolean): Promise<void> {
    this.autoTrading = enabled;
    this.logger.log(`Auto trading ${enabled ? 'enabled' : 'disabled'}`);
    this.eventEmitter.emit('autoTrading.changed', { enabled });
  }

  isAutoTradingEnabled(): boolean {
    return this.autoTrading;
  }

  async handleDecisionEvent(decision: DecisionEvent): Promise<void> {
    if (!this.autoTrading) {
      this.logger.log(`Skipping decision - auto trading disabled`);
      this.eventEmitter.emit('decision.skipped', {
        reason: 'Auto trading disabled',
        decision,
      });
      return;
    }

    try {
      // Convert decision to order request
      const orderRequest: OrderRequest = {
        symbol: decision.symbol,
        side: decision.action as 'BUY' | 'SELL',
        type: decision.type,
        quantity: decision.quantity,
        venue: decision.venue,
        price: decision.price,
      };

      await this.placeOrder(orderRequest);
    } catch (error) {
      this.logger.error(`Failed to execute decision: ${error}`);
      this.eventEmitter.emit('decision.failed', {
        decision,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }

  private handleOrderUpdate(update: OrderUpdateEvent) {
    const order = this.activeOrders.get(update.orderId);
    if (!order) {
      return;
    }

    // Update order status
    order.status = update.status;
    if (update.executedQty !== undefined) {
      order.executedQty = update.executedQty;
    }

    // Handle filled orders
    if (update.status === 'FILLED' && update.executedPrice) {
      this.updatePosition(order, update.executedPrice);
      this.activeOrders.delete(update.orderId);
    }

    // Handle canceled or rejected orders
    if (update.status === 'CANCELED' || update.status === 'REJECTED') {
      this.activeOrders.delete(update.orderId);
    }
  }

  private updatePosition(order: OrderResponse, executedPrice: number) {
    const key = order.symbol;
    const existingPosition = this.positions.get(key);

    if (!existingPosition) {
      // Create new position
      const position: Position = {
        symbol: order.symbol,
        side: order.side === 'BUY' ? 'LONG' : 'SHORT',
        quantity: order.quantity,
        entryPrice: executedPrice,
        currentPrice: executedPrice,
        pnl: 0,
        pnlPercent: 0,
        venue: (order as any).venue || 'SPOT',
        timestamp: Date.now(),
      };
      this.positions.set(key, position);
    } else {
      // Update existing position
      if (
        (existingPosition.side === 'LONG' && order.side === 'BUY') ||
        (existingPosition.side === 'SHORT' && order.side === 'SELL')
      ) {
        // Adding to position
        const totalCost =
          existingPosition.quantity * existingPosition.entryPrice + order.quantity * executedPrice;
        existingPosition.quantity += order.quantity;
        existingPosition.entryPrice = totalCost / existingPosition.quantity;
      } else {
        // Reducing or closing position
        existingPosition.quantity -= order.quantity;
        if (existingPosition.quantity <= 0) {
          this.positions.delete(key);
        }
      }
    }

    this.eventEmitter.emit('position.updated', this.positions.get(key));
  }
}
