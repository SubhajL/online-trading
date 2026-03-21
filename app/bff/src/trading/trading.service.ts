import {
  ConflictException,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleInit,
} from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CONTRACT_TOPICS } from '../contracts/topics';
import type { OrderUpdateV1 } from '../contracts/gen';
import { EngineClientService } from '../engine-client/engine-client.service';
import {
  RouterClientService,
  OrderRequest,
  OrderResponse,
  type RouterBracketPlacementResponse,
} from '../router-client/router-client.service';
import type { EmergencyCloseScope } from './dto/emergency-close.dto';
import { OrderRepository } from '../orders/repositories/order.repository';
import type { OrderType as EntityOrderType, OrderStatus } from '../orders/entities/order-entity';
import { generateClientOrderId, mapRouterErrorToHttpException } from './mappers/order.mapper';
import type { OrderEntity } from '../orders/entities/order-entity';

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
  status: OrderStatus;
  executedQty?: number;
  executedPrice?: number;
  timestamp?: number;
}

const orderUpdateStatusMap: Record<OrderUpdateV1['status'], OrderStatus> = {
  pending: 'NEW',
  new: 'NEW',
  partially_filled: 'PARTIALLY_FILLED',
  filled: 'FILLED',
  cancelled: 'CANCELED',
  rejected: 'REJECTED',
  expired: 'EXPIRED',
};

function parseContractNumber(value: string | null | undefined): number | undefined {
  if (value == null || value === '') {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseContractTimestamp(value: string): number | undefined {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? undefined : parsed;
}

function mapOrderResponseToUpdateEvent(order: OrderResponse): OrderUpdateEvent {
  return {
    orderId: order.orderId,
    symbol: order.symbol,
    status: order.status as OrderStatus,
    executedQty: order.executedQty,
    executedPrice: order.price,
    timestamp: order.updatedAt ? parseContractTimestamp(order.updatedAt) : undefined,
  };
}

function mapContractUpdateToEvent(orderId: string, update: OrderUpdateV1): OrderUpdateEvent {
  return {
    orderId,
    symbol: update.symbol,
    status: orderUpdateStatusMap[update.status],
    executedQty: parseContractNumber(update.filled_quantity),
    executedPrice:
      parseContractNumber(update.average_fill_price) ?? parseContractNumber(update.price),
    timestamp: parseContractTimestamp(update.update_time),
  };
}

function mapPersistedOrderToResponse(order: OrderEntity): OrderResponse {
  return {
    orderId: order.orderId,
    status: order.status,
    symbol: order.symbol,
    side: order.side,
    type: order.type,
    quantity: order.quantity,
    price: order.price ?? undefined,
    executedQty: order.filledQuantity,
    venue: order.venue,
    createdAt: order.createdAt.toISOString(),
    updatedAt: order.updatedAt.toISOString(),
  };
}

function mapPlacementToResponse(
  request: OrderRequest,
  placement: RouterBracketPlacementResponse,
): OrderResponse {
  return {
    orderId: placement.bracket_order_id,
    status: placement.partial_failure ? 'REJECTED' : 'NEW',
    symbol: placement.symbol,
    side: placement.side,
    type: request.type,
    quantity: placement.quantity,
    price: request.price,
    executedQty: 0,
    venue: request.venue,
    createdAt: placement.created_at ?? new Date().toISOString(),
    updatedAt: placement.created_at ?? new Date().toISOString(),
  };
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
    this.engineClient.subscribe(CONTRACT_TOPICS.orderUpdateV1, async (event: OrderUpdateV1) => {
      await this.handleOrderUpdate(event);
    });
  }

  async placeOrder(request: OrderRequest): Promise<OrderResponse> {
    const now = new Date();

    try {
      this.logger.log(`Placing order: ${JSON.stringify(request)}`);

      const placement = await this.routerClient.placeOrder(request);
      const clientOrderId = placement.client_order_ids.main || generateClientOrderId();
      const response = mapPlacementToResponse(request, placement);

      // Save order to database so it appears on /trades and /history pages
      await this.orderRepository.save({
        orderId: response.orderId,
        clientOrderId,
        symbol: request.symbol,
        side: request.side,
        type: mapOrderType(request.type),
        quantity: request.quantity,
        price: request.price || null,
        stopPrice: request.stopLossPrice,
        status: response.status as OrderStatus,
        venue: request.venue || 'SPOT',
        timeInForce: 'GTC',
        filledQuantity: response.executedQty || 0,
        createdAt: now,
        updatedAt: now,
      });

      // Track the active order in memory
      this.activeOrders.set(response.orderId, response);

      // Emit order update event (multi-tab sync via WebSocket)
      this.eventEmitter.emit(
        CONTRACT_TOPICS.orderUpdateV1,
        mapOrderResponseToUpdateEvent(response),
      );

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
    const persisted = await this.orderRepository.findByOrderId(orderId, venue);
    if (!persisted) {
      throw new NotFoundException('Order not found');
    }
    return mapPersistedOrderToResponse(persisted);
  }

  async cancelOrder(
    orderId: string,
    symbol: string,
    venue: 'SPOT' | 'USD_M',
  ): Promise<OrderResponse> {
    const persisted = await this.orderRepository.findByOrderId(orderId, venue);
    if (!persisted) {
      throw new NotFoundException('Order not found');
    }
    if (!persisted.exchangeOrderId && !persisted.clientOrderId) {
      throw new ConflictException('Order has no cancel identifier');
    }

    await this.routerClient.cancelOrder({
      symbol: persisted.symbol,
      venue: persisted.venue,
      orderId,
      exchangeOrderId: persisted.exchangeOrderId,
      clientOrderId: persisted.clientOrderId,
    });

    await this.orderRepository.update(orderId, {
      status: 'CANCELED',
      updatedAt: new Date(),
    } as Partial<OrderEntity>);

    const response: OrderResponse = {
      ...mapPersistedOrderToResponse(persisted),
      status: 'CANCELED',
      updatedAt: new Date().toISOString(),
    };

    // Remove from active orders
    this.activeOrders.delete(orderId);

    // Emit order update event
    this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, mapOrderResponseToUpdateEvent(response));

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
        stopLossPrice: decision.stopLoss as number,
        takeProfitPrice: decision.takeProfit as number,
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

  private async handleOrderUpdate(update: OrderUpdateV1): Promise<void> {
    const persisted = await this.findOrderForUpdate(update);
    if (!persisted) {
      this.logger.warn(
        `Ignoring order update without persisted match: clientOrderId=${update.client_order_id} exchangeOrderId=${update.order_id}`,
      );
      return;
    }

    const normalizedUpdate = mapContractUpdateToEvent(persisted.orderId, update);
    const updatedAt = new Date();
    const lastUpdateTime = new Date(update.update_time);
    const updates: Partial<OrderEntity> = {
      status: normalizedUpdate.status,
      filledQuantity: normalizedUpdate.executedQty ?? persisted.filledQuantity,
      averageFillPrice: normalizedUpdate.executedPrice ?? persisted.averageFillPrice,
      exchangeOrderId: update.order_id || persisted.exchangeOrderId,
      rejectReason: update.error_message ?? persisted.rejectReason,
      lastUpdateTime: Number.isNaN(lastUpdateTime.getTime())
        ? persisted.lastUpdateTime
        : lastUpdateTime,
      updatedAt,
    };
    await this.orderRepository.update(persisted.orderId, updates);

    const order: OrderResponse = {
      ...mapPersistedOrderToResponse({
        ...persisted,
        ...updates,
      }),
      updatedAt: updatedAt.toISOString(),
    };

    if (normalizedUpdate.executedQty !== undefined) {
      order.executedQty = normalizedUpdate.executedQty;
    }

    if (normalizedUpdate.status === 'FILLED' && normalizedUpdate.executedPrice !== undefined) {
      this.updatePosition(order, normalizedUpdate.executedPrice);
      this.activeOrders.delete(order.orderId);
    } else if (
      normalizedUpdate.status === 'CANCELED' ||
      normalizedUpdate.status === 'REJECTED' ||
      normalizedUpdate.status === 'EXPIRED'
    ) {
      this.activeOrders.delete(order.orderId);
    } else {
      this.activeOrders.set(order.orderId, order);
    }

    this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, normalizedUpdate);
  }

  private async findOrderForUpdate(update: OrderUpdateV1): Promise<OrderEntity | null> {
    if (update.client_order_id) {
      const matchedByClientOrderId = await this.orderRepository.findByClientOrderId(
        update.client_order_id,
        update.venue as 'SPOT' | 'USD_M',
      );
      if (matchedByClientOrderId) {
        return matchedByClientOrderId;
      }
    }

    if (update.order_id) {
      return this.orderRepository.findByExchangeOrderId(
        update.order_id,
        update.venue as 'SPOT' | 'USD_M',
      );
    }

    return null;
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
