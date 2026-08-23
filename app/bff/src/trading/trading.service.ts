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
import {
  OrderRepository,
  type LockedOrderUpdate,
  type PositionSnapshot,
} from '../orders/repositories/order.repository';
import type { OrderType as EntityOrderType, OrderStatus } from '../orders/entities/order-entity';
import { generateClientOrderId, mapRouterErrorToHttpException } from './mappers/order.mapper';
import type { OrderEntity } from '../orders/entities/order-entity';
import { createRouterPlacementIdentity } from './placement-identity';
import type { RouterPlacementIdentity } from './placement-identity';

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

function positionKey(venue: Position['venue'], symbol: string): string {
  return `${venue}:${symbol}`;
}

function snapshotToPosition(snapshot: PositionSnapshot): Position | undefined {
  const quantity = parseContractNumber(snapshot.size);
  const entryPrice = parseContractNumber(snapshot.entryPrice);
  const currentPrice = parseContractNumber(snapshot.currentPrice);
  const pnl = parseContractNumber(snapshot.unrealizedPnl);
  const side =
    snapshot.side === 'BUY' || snapshot.side === 'LONG'
      ? 'LONG'
      : snapshot.side === 'SELL' || snapshot.side === 'SHORT'
        ? 'SHORT'
        : undefined;
  if (
    quantity === undefined ||
    quantity <= 0 ||
    entryPrice === undefined ||
    entryPrice <= 0 ||
    currentPrice === undefined ||
    currentPrice <= 0 ||
    pnl === undefined ||
    side === undefined
  ) {
    return undefined;
  }

  const timestampValue =
    snapshot.updatedAt instanceof Date
      ? snapshot.updatedAt.getTime()
      : Date.parse(String(snapshot.updatedAt));
  const notional = entryPrice * quantity;
  const pnlPercent = notional > 0 && Number.isFinite(notional) ? (pnl / notional) * 100 : 0;
  return {
    symbol: snapshot.symbol,
    side,
    quantity,
    entryPrice,
    currentPrice,
    pnl,
    pnlPercent: Number.isFinite(pnlPercent) ? pnlPercent : 0,
    venue: snapshot.venue,
    timestamp: Number.isFinite(timestampValue) ? timestampValue : Date.now(),
  };
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

function parseContractNumber(value: string | number | null | undefined): number | undefined {
  if (value == null || value === '') {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

type ExactDecimal = {
  scaled: bigint;
  text: string;
};

const exactDecimalScale = 100_000_000n;
const zeroExactDecimal: ExactDecimal = { scaled: 0n, text: '0' };

function parseExactDecimal(
  value: string | number | null | undefined,
): ExactDecimal | null | undefined {
  if (value == null || value === '') {
    return null;
  }
  const text = typeof value === 'number' ? String(value) : value;
  const match = /^(\d+)(?:\.(\d+))?$/.exec(text);
  if (!match || match[1].length > 10 || (match[2]?.length ?? 0) > 8) {
    return undefined;
  }
  const fraction = (match[2] ?? '').padEnd(8, '0');
  return {
    scaled: BigInt(match[1]) * exactDecimalScale + BigInt(fraction || '0'),
    text,
  };
}

function decimalForLockedUpdate(value: ExactDecimal, preferNumber: boolean): string | number {
  if (!preferNumber) {
    return value.text;
  }
  const numeric = Number(value.text);
  const roundTrip = parseExactDecimal(numeric);
  return Number.isFinite(numeric) && roundTrip?.scaled === value.scaled ? numeric : value.text;
}

function usesNumericProjectionValues(order: OrderEntity): boolean {
  return [
    order.quantity,
    order.price,
    order.stopPrice,
    order.filledQuantity,
    order.averageFillPrice,
  ].some((value) => typeof value === 'number');
}

function nullableNumericIdentityMatches(
  persisted: string | number | null | undefined,
  incoming: string | null | undefined,
): boolean {
  const persistedValue = parseExactDecimal(persisted);
  if (incoming === null) {
    return persistedValue === null;
  }
  const incomingValue = parseExactDecimal(incoming);
  return (
    persistedValue !== null &&
    persistedValue !== undefined &&
    incomingValue !== null &&
    incomingValue !== undefined &&
    persistedValue.scaled === incomingValue.scaled
  );
}

function isValidOrderUpdateState(
  status: OrderStatus | undefined,
  quantity: ExactDecimal | null | undefined,
  filledQuantity: ExactDecimal | null | undefined,
  averageFillPrice: ExactDecimal | null | undefined,
): boolean {
  if (
    !status ||
    quantity === null ||
    quantity === undefined ||
    quantity.scaled <= 0n ||
    filledQuantity === null ||
    filledQuantity === undefined ||
    filledQuantity.scaled < 0n ||
    filledQuantity.scaled > quantity.scaled ||
    averageFillPrice === undefined
  ) {
    return false;
  }

  if (status === 'NEW') {
    return filledQuantity.scaled === 0n && averageFillPrice === null;
  }
  if (status === 'PARTIALLY_FILLED') {
    return (
      filledQuantity.scaled > 0n &&
      filledQuantity.scaled < quantity.scaled &&
      averageFillPrice !== null &&
      averageFillPrice.scaled > 0n
    );
  }
  if (status === 'FILLED') {
    return (
      filledQuantity.scaled === quantity.scaled &&
      averageFillPrice !== null &&
      averageFillPrice.scaled > 0n
    );
  }
  if (terminalOrderStatuses.has(status)) {
    return filledQuantity.scaled === 0n
      ? averageFillPrice === null
      : averageFillPrice !== null && averageFillPrice.scaled > 0n;
  }
  return false;
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

function normalizeVenue(value: string): 'SPOT' | 'USD_M' | null {
  const venue = value.trim().toUpperCase();
  return venue === 'SPOT' || venue === 'USD_M' ? venue : null;
}

function mapContractOrderType(value: string): EntityOrderType | null {
  const orderTypeMap: Record<string, EntityOrderType> = {
    MARKET: 'MARKET',
    LIMIT: 'LIMIT',
    STOP_MARKET: 'STOP_LOSS',
    STOP_LOSS: 'STOP_LOSS',
    STOP_LIMIT: 'STOP_LOSS_LIMIT',
    STOP_LOSS_LIMIT: 'STOP_LOSS_LIMIT',
  };
  return orderTypeMap[value.trim().toUpperCase()] ?? null;
}

function mapPersistedOrderToUpdateEvent(order: OrderEntity): OrderUpdateEvent {
  const timestamp = order.lastUpdateTime ?? order.updatedAt;
  return {
    orderId: order.orderId,
    symbol: order.symbol,
    status: order.status,
    executedQty: parseContractNumber(order.filledQuantity) ?? 0,
    executedPrice: parseContractNumber(order.averageFillPrice),
    timestamp: timestamp ? timestamp.getTime() : undefined,
  };
}

const terminalOrderStatuses = new Set<OrderStatus>(['FILLED', 'CANCELED', 'REJECTED', 'EXPIRED']);

class ImmutableOrderUpdateError extends Error {}

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
  private readonly positionRefreshTails = new Map<string, Promise<void>>();
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
    const positionSnapshots = await this.orderRepository.findActivePositionSnapshots();
    this.positions.clear();
    for (const snapshot of positionSnapshots) {
      const position = snapshotToPosition(snapshot);
      if (position) {
        this.positions.set(positionKey(position.venue, position.symbol), position);
      }
    }
    this.logger.log(`Recovered ${activeOrders.length} active orders from database`);
  }

  private async refreshPositionProjection(venue: Position['venue'], symbol: string): Promise<void> {
    const key = positionKey(venue, symbol);
    const previous = this.positionRefreshTails.get(key) ?? Promise.resolve();
    const refresh = previous
      .catch(() => undefined)
      .then(async () => {
        const snapshots = await this.orderRepository.findActivePositionSnapshots({ venue, symbol });
        const snapshot = snapshots.find(
          (candidate) => candidate.venue === venue && candidate.symbol === symbol,
        );
        const projection = snapshot ? snapshotToPosition(snapshot) : undefined;
        if (projection) {
          this.positions.set(key, projection);
        } else {
          this.positions.delete(key);
        }
        this.eventEmitter.emit(CONTRACT_TOPICS.positionUpdateV1, projection);
      });
    const tail = refresh.finally(() => {
      if (this.positionRefreshTails.get(key) === tail) {
        this.positionRefreshTails.delete(key);
      }
    });
    this.positionRefreshTails.set(key, tail);
    await tail;
  }

  private subscribeToEngineEvents() {
    // Rejections must be contained: an engine-event listener's unhandled
    // rejection kills the whole Node process (2026-07-11 soak incident).
    this.engineClient.subscribe(CONTRACT_TOPICS.decisionV1, (event: DecisionEvent) => {
      this.eventEmitter.emit(CONTRACT_TOPICS.decisionV1, event);
      void this.handleDecisionEvent(event).catch((error) => {
        this.logger.error(`Failed to handle decision event: ${error}`);
      });
    });

    this.engineClient.subscribe(CONTRACT_TOPICS.orderUpdateV1, (event: OrderUpdateV1) => {
      void this.handleOrderUpdate(event).catch((error) => {
        this.logger.error(`Failed to handle order update: ${error}`);
      });
    });
  }

  async placeOrder(
    request: OrderRequest,
    identity: RouterPlacementIdentity,
  ): Promise<OrderResponse> {
    const now = new Date();

    try {
      this.logger.log(`Placing order: ${JSON.stringify(request)}`);

      const placement = await this.routerClient.placeOrder(request, identity);
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

      const decisionKey = JSON.stringify({
        symbol: decision.symbol,
        action: decision.action,
        quantity: decision.quantity,
        venue: decision.venue,
        type: decision.type,
        price: decision.price,
        stopLoss: decision.stopLoss,
        takeProfit: decision.takeProfit,
        timestamp: decision.timestamp,
      });
      await this.placeOrder(
        orderRequest,
        createRouterPlacementIdentity('engine-decision', decisionKey, 1),
      );
    } catch (error) {
      this.logger.error(`Failed to execute decision: ${error}`);
      this.eventEmitter.emit(CONTRACT_TOPICS.decisionFailedV1, {
        decision,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }

  private async handleOrderUpdate(update: OrderUpdateV1): Promise<void> {
    const accepted = await this.reconcileOrderUpdate(update);
    if (accepted) {
      this.eventEmitter.emit(CONTRACT_TOPICS.orderUpdateV1, accepted.event);
    }
  }

  async acceptOrderUpdate(update: OrderUpdateV1): Promise<OrderUpdateEvent | null> {
    const accepted = await this.reconcileOrderUpdate(update);
    return accepted?.event ?? null;
  }

  private async reconcileOrderUpdate(
    update: OrderUpdateV1,
  ): Promise<{ event: OrderUpdateEvent; updated: boolean } | null> {
    const venue = normalizeVenue(update.venue);
    const symbol = update.symbol.trim();
    const clientOrderId = update.client_order_id.trim();
    const exchangeOrderId = update.order_id.trim();
    if (!venue || !symbol || (!clientOrderId && !exchangeOrderId)) {
      this.logger.warn(
        `Ignoring order update without persisted match: clientOrderId=${update.client_order_id} exchangeOrderId=${update.order_id}`,
      );
      return null;
    }

    let accepted;
    try {
      accepted = await this.orderRepository.withLockedOrderForUpdate(
        {
          venue,
          symbol,
          clientOrderId,
          exchangeOrderId,
        },
        (persisted) => {
          const mappedOrderType = mapContractOrderType(update.order_type);
          const incomingQuantity = parseExactDecimal(update.quantity);
          const persistedQuantity = parseExactDecimal(persisted.quantity);
          const side = update.side.trim().toUpperCase();
          const decisionId = update.decision_id.trim() || null;
          const exchangeOrderId = update.order_id.trim();
          const persistedExchangeOrderId = persisted.exchangeOrderId?.trim() || '';
          const incomingUpdateTime = new Date(update.update_time);
          const incomingStatus = orderUpdateStatusMap[update.status];
          const incomingFilledQuantity = parseExactDecimal(update.filled_quantity);
          const incomingAverageFillPrice = parseExactDecimal(update.average_fill_price);
          const status =
            persisted.status === 'PARTIALLY_FILLED' && incomingStatus === 'NEW'
              ? persisted.status
              : incomingStatus;
          const currentFilledQuantity = parseExactDecimal(persisted.filledQuantity);
          const isSyntheticUpdate = exchangeOrderId === '';
          const isStrictlyNewerUpdate =
            !isSyntheticUpdate &&
            !Number.isNaN(incomingUpdateTime.getTime()) &&
            (!persisted.lastUpdateTime || incomingUpdateTime > persisted.lastUpdateTime);
          const isSameStatusAverageCorrection =
            isStrictlyNewerUpdate &&
            (persisted.status === 'PARTIALLY_FILLED' || persisted.status === 'FILLED') &&
            incomingStatus === persisted.status &&
            incomingFilledQuantity !== null &&
            incomingFilledQuantity !== undefined &&
            currentFilledQuantity !== null &&
            currentFilledQuantity !== undefined &&
            currentFilledQuantity.scaled > 0n &&
            incomingFilledQuantity.scaled === currentFilledQuantity.scaled &&
            incomingAverageFillPrice !== null &&
            incomingAverageFillPrice !== undefined &&
            incomingAverageFillPrice.scaled > 0n;
          const isSyntheticPartialReplay =
            isSyntheticUpdate &&
            incomingStatus === 'NEW' &&
            persisted.status === 'PARTIALLY_FILLED' &&
            incomingFilledQuantity?.scaled === 0n &&
            incomingAverageFillPrice === null;
          const canUpgradeTerminalFill =
            (persisted.status === 'CANCELED' || persisted.status === 'EXPIRED') &&
            incomingStatus === 'FILLED' &&
            incomingQuantity !== null &&
            incomingQuantity !== undefined &&
            incomingFilledQuantity !== null &&
            incomingFilledQuantity !== undefined &&
            currentFilledQuantity !== null &&
            currentFilledQuantity !== undefined &&
            incomingFilledQuantity.scaled === incomingQuantity.scaled &&
            incomingFilledQuantity.scaled > currentFilledQuantity.scaled;
          if (
            (clientOrderId !== '' && persisted.clientOrderId !== clientOrderId) ||
            persisted.venue !== venue ||
            persisted.symbol.trim().toUpperCase() !== symbol.toUpperCase() ||
            persisted.side !== side ||
            persisted.type !== mappedOrderType ||
            incomingQuantity === null ||
            incomingQuantity === undefined ||
            persistedQuantity === null ||
            persistedQuantity === undefined ||
            persistedQuantity.scaled !== incomingQuantity.scaled ||
            (persisted.decisionId != null && persisted.decisionId !== decisionId) ||
            (exchangeOrderId !== '' &&
              persistedExchangeOrderId !== '' &&
              persistedExchangeOrderId !== exchangeOrderId) ||
            !nullableNumericIdentityMatches(persisted.price, update.price) ||
            !nullableNumericIdentityMatches(persisted.stopPrice, update.stop_price)
          ) {
            throw new ImmutableOrderUpdateError('order update immutable identity mismatch');
          }
          if (
            !isSyntheticPartialReplay &&
            !isValidOrderUpdateState(
              status,
              incomingQuantity,
              incomingFilledQuantity,
              incomingAverageFillPrice,
            )
          ) {
            throw new ImmutableOrderUpdateError('order update has invalid relational state');
          }
          if (isSyntheticPartialReplay) {
            return null;
          }
          if (
            !isSyntheticUpdate &&
            persisted.lastUpdateTime &&
            !Number.isNaN(incomingUpdateTime.getTime()) &&
            incomingUpdateTime < persisted.lastUpdateTime
          ) {
            return null;
          }
          if (
            terminalOrderStatuses.has(persisted.status) &&
            !canUpgradeTerminalFill &&
            !isSameStatusAverageCorrection
          ) {
            return null;
          }

          const currentAverageFillPrice = parseExactDecimal(persisted.averageFillPrice);
          if (
            currentFilledQuantity === undefined ||
            incomingFilledQuantity === null ||
            incomingFilledQuantity === undefined ||
            currentAverageFillPrice === undefined ||
            incomingAverageFillPrice === undefined
          ) {
            throw new ImmutableOrderUpdateError('order update has invalid decimal values');
          }
          const currentEffectiveFilledQuantity = currentFilledQuantity ?? zeroExactDecimal;
          const fillIncreased =
            incomingFilledQuantity.scaled > currentEffectiveFilledQuantity.scaled;
          const preferNumericUpdate = usesNumericProjectionValues(persisted);
          const effectiveAverageFillPrice =
            incomingAverageFillPrice !== null &&
            (currentAverageFillPrice === null || fillIncreased || isSameStatusAverageCorrection)
              ? incomingAverageFillPrice
              : currentAverageFillPrice;
          const nextExchangeOrderId = exchangeOrderId || persisted.exchangeOrderId;
          const lastUpdateTime =
            !isSyntheticUpdate &&
            !Number.isNaN(incomingUpdateTime.getTime()) &&
            (!persisted.lastUpdateTime || incomingUpdateTime > persisted.lastUpdateTime)
              ? incomingUpdateTime
              : persisted.lastUpdateTime;
          const nextDecisionId = persisted.decisionId ?? decisionId;
          const updates: LockedOrderUpdate = {};

          updates.status = status;
          if (fillIncreased) {
            updates.filledQuantity = decimalForLockedUpdate(
              incomingFilledQuantity,
              preferNumericUpdate,
            );
          } else if (preferNumericUpdate && typeof persisted.filledQuantity === 'number') {
            updates.filledQuantity = persisted.filledQuantity;
          }
          if (
            effectiveAverageFillPrice !== null &&
            (currentAverageFillPrice === null ||
              effectiveAverageFillPrice.scaled !== currentAverageFillPrice.scaled)
          ) {
            updates.averageFillPrice = decimalForLockedUpdate(
              effectiveAverageFillPrice,
              preferNumericUpdate,
            );
          } else if (preferNumericUpdate && typeof persisted.averageFillPrice === 'number') {
            updates.averageFillPrice = persisted.averageFillPrice;
          }
          updates.exchangeOrderId = nextExchangeOrderId;
          if (nextDecisionId !== persisted.decisionId) {
            updates.decisionId = nextDecisionId;
          }
          if (canUpgradeTerminalFill && persisted.rejectReason != null) {
            updates.rejectReason = null;
          } else if (
            update.error_message != null &&
            update.error_message !== persisted.rejectReason
          ) {
            updates.rejectReason = update.error_message;
          }
          if (lastUpdateTime?.getTime() !== persisted.lastUpdateTime?.getTime()) {
            updates.lastUpdateTime = lastUpdateTime;
          }
          if (Object.keys(updates).length === 0) {
            return null;
          }
          updates.updatedAt = new Date();
          return updates;
        },
      );
    } catch (error) {
      if (error instanceof ImmutableOrderUpdateError) {
        this.logger.warn(
          `Ignoring order update with immutable identity mismatch: clientOrderId=${clientOrderId} exchangeOrderId=${exchangeOrderId}`,
        );
        return null;
      }
      throw error;
    }
    if (!accepted) {
      this.logger.warn(
        `Ignoring order update without compatible persisted match: clientOrderId=${clientOrderId} exchangeOrderId=${exchangeOrderId}`,
      );
      return null;
    }

    const normalizedUpdate = mapPersistedOrderToUpdateEvent(accepted.order);
    const order = mapPersistedOrderToResponse(accepted.order);
    if (normalizedUpdate.status === 'FILLED') {
      this.activeOrders.delete(order.orderId);
    } else if (terminalOrderStatuses.has(normalizedUpdate.status)) {
      this.activeOrders.delete(order.orderId);
    } else {
      this.activeOrders.set(order.orderId, order);
    }

    await this.refreshPositionProjection(accepted.order.venue, accepted.order.symbol);

    return { event: normalizedUpdate, updated: accepted.updated };
  }
}
