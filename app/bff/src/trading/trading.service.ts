import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CONTRACT_TOPICS } from '../contracts/topics';
import { EngineClientService } from '../engine-client/engine-client.service';
import {
  RouterClientService,
  OrderRequest,
  OrderResponse,
} from '../router-client/router-client.service';
import type { EmergencyCloseScope } from './dto/emergency-close.dto';
import { OrderRepository } from '../orders/repositories/order.repository';
import type { OrderType as EntityOrderType, OrderStatus } from '../orders/entities/order-entity';
import { generateClientOrderId, mapRouterErrorToHttpException } from './mappers/order.mapper';

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
  entry?: number;
  stopLoss?: number;
  takeProfit?: number;
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

// Map request order types to entity order types
function mapOrderType(requestType: string): EntityOrderType {
  const typeMap: Record<string, EntityOrderType> = {
    MARKET: 'MARKET',
    LIMIT: 'LIMIT',
    STOP: 'STOP_LOSS',
    STOP_MARKET: 'STOP_LOSS',
    STOP_LOSS: 'STOP_LOSS',
    STOP_LOSS_LIMIT: 'STOP_LOSS_LIMIT',
    TAKE_PROFIT: 'TAKE_PROFIT',
    TAKE_PROFIT_LIMIT: 'TAKE_PROFIT_LIMIT',
  };
  return typeMap[requestType] || 'MARKET';
}

@Injectable()
export class TradingService implements OnModuleInit {
  private readonly logger = new Logger(TradingService.name);
  private readonly positions = new Map<string, Position>();
  private readonly activeOrders = new Map<string, OrderResponse>();
  private autoTrading = false;

  constructor(
    private readonly engineClient: EngineClientService,
    private readonly routerClient: RouterClientService,
    private readonly eventEmitter: EventEmitter2,
    private readonly orderRepository: OrderRepository,
  ) {
    this.subscribeToEngineEvents();
  }

  async onModuleInit(): Promise<void> {
    const activeOrders = await this.orderRepository.findActiveOrders();
    for (const order of activeOrders) {
      this.activeOrders.set(order.orderId, {
        orderId: order.orderId,
        status: order.status,
        symbol: order.symbol,
        side: order.side,
        type: order.type,
        quantity: order.quantity,
        price: order.price ?? undefined,
        executedQty: order.filledQuantity,
        venue: order.venue,
      });
    }
    this.logger.log(`Recovered ${activeOrders.length} active orders from database`);
  }

  private subscribeToEngineEvents() {
    // Subscribe to decision events from engine
    this.engineClient.subscribe(CONTRACT_TOPICS.decisionV1, (event: DecisionEvent) => {
      this.eventEmitter.emit(CONTRACT_TOPICS.decisionV1, event);
      this.handleDecisionEvent(event);
    });

    // Subscribe to order update events
    this.engineClient.subscribe(CONTRACT_TOPICS.orderUpdateV1, (event: OrderUpdateEvent) => {
      this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, event);
      this.handleOrderUpdate(event);
    });
  }

  async placeOrder(request: OrderRequest): Promise<OrderResponse> {
    const clientOrderId = generateClientOrderId();
    const now = new Date();

    try {
      this.logger.log(`Placing order: ${JSON.stringify(request)}`);

      const response = await this.routerClient.placeOrder(request);

      // Save order to database so it appears on /trades and /history pages
      await this.orderRepository.save({
        orderId: response.orderId,
        clientOrderId,
        symbol: request.symbol,
        side: request.side,
        type: mapOrderType(request.type),
        quantity: request.quantity,
        price: request.price || null,
        status: response.status as OrderStatus,
        venue: request.venue || 'SPOT',
        timeInForce: request.timeInForce || 'GTC',
        filledQuantity: response.executedQty || 0,
        createdAt: now,
        updatedAt: now,
      });

      // Track the active order in memory
      this.activeOrders.set(response.orderId, response);

      // Emit order update event (multi-tab sync via WebSocket)
      this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, response);

      return response;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      this.logger.error(`Failed to place order: ${errorMessage}`);

      this.eventEmitter.emit(CONTRACT_TOPICS.orderFailedV1, {
        request,
        error: errorMessage,
      });

      throw mapRouterErrorToHttpException(error);
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

    // Emit order update event
    this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, response);

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
    this.eventEmitter.emit(CONTRACT_TOPICS.autoTradingV1, { enabled });
  }

  isAutoTradingEnabled(): boolean {
    return this.autoTrading;
  }

  async emergencyClose(
    scope: EmergencyCloseScope,
    stopEngine: boolean = false,
  ): Promise<{ success: boolean; closedCount: number }> {
    this.logger.warn(`Emergency close triggered: scope=${scope}, stopEngine=${stopEngine}`);

    let closedCount = 0;

    try {
      // Close positions based on scope
      if (scope === 'ALL' || scope === 'SPOT') {
        const spotResult = await this.routerClient.closeAllPositions({
          is_futures: false,
        });
        if (spotResult.success) {
          closedCount += 1; // Router doesn't return count, so we estimate
        }
      }

      if (scope === 'ALL' || scope === 'FUTURES') {
        const futuresResult = await this.routerClient.closeAllPositions({
          is_futures: true,
        });
        if (futuresResult.success) {
          closedCount += 1;
        }
      }

      // Clear local position cache
      if (scope === 'ALL') {
        this.positions.clear();
      } else {
        // Clear only positions for the specified venue
        const venueToFilter = scope === 'SPOT' ? 'SPOT' : 'USD_M';
        for (const [key, position] of this.positions) {
          if (position.venue === venueToFilter) {
            this.positions.delete(key);
          }
        }
      }

      // Clear active orders
      this.activeOrders.clear();

      // Optionally stop auto trading
      if (stopEngine) {
        await this.setAutoTrading(false);
      }

      this.eventEmitter.emit('emergency.close', {
        scope,
        closedCount,
        stopEngine,
        timestamp: Date.now(),
      });

      this.logger.log(`Emergency close completed: closedCount=${closedCount}`);
      return { success: true, closedCount };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      this.logger.error(`Emergency close failed: ${errorMessage}`);

      this.eventEmitter.emit('emergency.close.failed', {
        scope,
        error: errorMessage,
        timestamp: Date.now(),
      });

      throw error;
    }
  }

  async handleDecisionEvent(decision: DecisionEvent): Promise<void> {
    if (!this.autoTrading) {
      this.logger.log(`Skipping decision - auto trading disabled`);
      this.eventEmitter.emit(CONTRACT_TOPICS.decisionSkippedV1, {
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
      this.eventEmitter.emit(CONTRACT_TOPICS.decisionFailedV1, {
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
        venue: order.venue || 'SPOT',
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

    this.eventEmitter.emit(CONTRACT_TOPICS.positionUpdateV1, this.positions.get(key));
  }
}
