import { Test, TestingModule } from '@nestjs/testing';
import { ValidationPipe } from '@nestjs/common';
import type { INestApplication } from '@nestjs/common';
import { GUARDS_METADATA } from '@nestjs/common/constants';
import request from 'supertest';
import type { OrderUpdateV1 } from '../contracts/gen';
import { InternalApiGuard } from '../auth/guards/internal-api.guard';
import { InternalTradingController } from './trading.controller';
import { TradingService } from './trading.service';

describe('InternalTradingController', () => {
  let controller: InternalTradingController;
  let app: INestApplication;
  const tradingService = {
    acceptOrderUpdate: jest.fn(),
  };

  const orderUpdate: OrderUpdateV1 = {
    version: '1.0.0',
    venue: 'USD_M',
    symbol: 'BTCUSDT',
    order_id: 'exchange-789',
    client_order_id: 'main-1',
    decision_id: 'decision-1',
    update_time: '2026-03-21T20:05:00Z',
    status: 'new',
    side: 'buy',
    order_type: 'limit',
    price: '45000',
    stop_price: null,
    quantity: '0.01',
    filled_quantity: '0',
    average_fill_price: null,
    commission: null,
    commission_asset: null,
    error_message: null,
    is_reduce_only: false,
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    const module: TestingModule = await Test.createTestingModule({
      controllers: [InternalTradingController],
      providers: [
        {
          provide: TradingService,
          useValue: tradingService,
        },
      ],
    })
      .overrideGuard(InternalApiGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(InternalTradingController);
    app = module.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
        forbidNonWhitelisted: true,
        transformOptions: { enableImplicitConversion: true },
      }),
    );
    await app.init();
  });

  afterEach(async () => {
    await app.close();
  });

  it('is protected by the internal API guard', () => {
    const guards = Reflect.getMetadata(GUARDS_METADATA, InternalTradingController);

    expect(guards).toContain(InternalApiGuard);
  });

  it('acknowledges an order update only after durable acceptance', async () => {
    tradingService.acceptOrderUpdate.mockResolvedValue({ orderId: 'bracket-123' });

    await expect(controller.acceptOrderUpdate(orderUpdate)).resolves.toEqual({ ok: true });
    expect(tradingService.acceptOrderUpdate).toHaveBeenCalledWith(orderUpdate);
  });

  it('rejects an order update without a persisted order match', async () => {
    tradingService.acceptOrderUpdate.mockResolvedValue(null);

    await expect(controller.acceptOrderUpdate(orderUpdate)).resolves.toEqual({ ok: false });
  });

  it('accepts a valid contract through the production validation pipeline', async () => {
    tradingService.acceptOrderUpdate.mockResolvedValue({ orderId: 'bracket-123' });

    await request(app.getHttpServer())
      .post('/internal/trading/order-update')
      .send(orderUpdate)
      .expect(200, { ok: true });

    expect(tradingService.acceptOrderUpdate).toHaveBeenCalledWith(orderUpdate);
  });

  it('accepts fixed-point scale-eight contract decimals', async () => {
    tradingService.acceptOrderUpdate.mockResolvedValue({ orderId: 'bracket-123' });
    const smallestTickUpdate = {
      ...orderUpdate,
      price: '0.00000001',
      quantity: '0.00000010',
    };

    await request(app.getHttpServer())
      .post('/internal/trading/order-update')
      .send(smallestTickUpdate)
      .expect(200, { ok: true });

    expect(tradingService.acceptOrderUpdate).toHaveBeenCalledWith(smallestTickUpdate);
  });

  it.each([
    ['unsupported version', { version: '2.0.0' }],
    ['unsupported status', { status: 'unknown' }],
    ['unsupported order type', { order_type: 'iceberg' }],
    ['invalid update time', { update_time: 'not-a-date' }],
    ['negative quantity', { quantity: '-1' }],
    ['quantity beyond database scale', { quantity: '0.123456789' }],
    ['quantity beyond database precision', { quantity: '10000000000.00000000' }],
    ['non-finite filled quantity', { filled_quantity: 'NaN' }],
    ['negative price', { price: '-1' }],
    ['unknown field', { unexpected: true }],
  ])('returns 400 before repository access for %s', async (_case, overrides) => {
    await request(app.getHttpServer())
      .post('/internal/trading/order-update')
      .send({ ...orderUpdate, ...overrides })
      .expect(400);

    expect(tradingService.acceptOrderUpdate).not.toHaveBeenCalled();
  });

  it('returns 400 before repository access for a missing required identity', async () => {
    const payload = { ...orderUpdate } as Record<string, unknown>;
    delete payload.client_order_id;

    await request(app.getHttpServer())
      .post('/internal/trading/order-update')
      .send(payload)
      .expect(400);

    expect(tradingService.acceptOrderUpdate).not.toHaveBeenCalled();
  });
});
