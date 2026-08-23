import { randomUUID } from 'node:crypto';
import { DataSource } from 'typeorm';
import { EventEmitter2 } from '@nestjs/event-emitter';
import type { OrderUpdateV1 } from '../../src/contracts/gen';
import { EngineClientService } from '../../src/engine-client/engine-client.service';
import { OrderEntity } from '../../src/orders/entities/order-entity';
import { OrderRepository } from '../../src/orders/repositories/order.repository';
import { RouterClientService } from '../../src/router-client/router-client.service';
import { TradingService } from '../../src/trading/trading.service';

const databaseUrl = process.env.TEST_DATABASE_URL;
const describeWithPostgres = databaseUrl ? describe : describe.skip;

describeWithPostgres('order update PostgreSQL reconciliation', () => {
  let admin: DataSource;
  let database: DataSource;
  let schema: string;
  let service: TradingService;

  const createUpdate = (overrides: Partial<OrderUpdateV1>): OrderUpdateV1 => ({
    version: '1.0.0',
    venue: 'USD_M',
    symbol: 'BTCUSDT',
    order_id: 'exchange-789',
    client_order_id: 'main-1',
    decision_id: '11111111-1111-4111-8111-111111111111',
    update_time: '2026-03-21T20:06:00Z',
    status: 'partially_filled',
    side: 'buy',
    order_type: 'limit',
    price: '45000',
    stop_price: null,
    quantity: '0.01',
    filled_quantity: '0.006',
    average_fill_price: '45005',
    commission: null,
    commission_asset: null,
    error_message: null,
    is_reduce_only: false,
    ...overrides,
  });

  beforeAll(async () => {
    admin = new DataSource({ type: 'postgres', url: databaseUrl });
    await admin.initialize();
    schema = `bff_order_lock_${process.pid}_${Date.now()}`;
    await admin.query(`CREATE SCHEMA "${schema}"`);

    database = new DataSource({
      type: 'postgres',
      url: databaseUrl,
      schema,
      entities: [OrderEntity],
      synchronize: true,
    });
    await database.initialize();
    await database.query(`
      CREATE TABLE "${schema}".positions (
        position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        venue TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        size NUMERIC(18,8) NOT NULL,
        entry_price NUMERIC(18,8) NOT NULL,
        current_price NUMERIC(18,8) NOT NULL,
        unrealized_pnl NUMERIC(18,8) NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE
      );
      CREATE UNIQUE INDEX uq_test_positions_active
        ON "${schema}".positions (venue, symbol) WHERE is_active = TRUE;
    `);
    const orderRepository = new OrderRepository(database.getRepository(OrderEntity));
    service = new TradingService(
      { subscribe: jest.fn() } as unknown as EngineClientService,
      {} as RouterClientService,
      { emit: jest.fn() } as unknown as EventEmitter2,
      orderRepository,
    );
  });

  afterAll(async () => {
    if (database?.isInitialized) {
      await database.destroy();
    }
    if (admin?.isInitialized) {
      await admin.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`);
      await admin.destroy();
    }
  });

  beforeEach(async () => {
    await database.getRepository(OrderEntity).clear();
    await database.query(`TRUNCATE TABLE "${schema}".positions`);
    (service as unknown as { positions: Map<string, unknown> }).positions.clear();
    await database.getRepository(OrderEntity).save({
      orderId: randomUUID(),
      clientOrderId: 'main-1',
      exchangeOrderId: 'exchange-789',
      decisionId: '11111111-1111-4111-8111-111111111111',
      venue: 'USD_M',
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.01,
      price: 45000,
      stopPrice: null,
      timeInForce: 'GTC',
      status: 'NEW',
      filledQuantity: 0,
      averageFillPrice: null,
      lastUpdateTime: new Date('2026-03-21T20:04:00Z'),
      commission: 0,
      commissionAsset: null,
      reduceOnly: false,
      postOnly: false,
      closePosition: false,
      activationPrice: null,
      callbackRate: null,
      workingType: null,
      priceProtect: false,
      rejectReason: null,
    });
    await database.query(`
      CREATE OR REPLACE FUNCTION "${schema}".delay_high_fill()
      RETURNS trigger AS $$
      BEGIN
        IF NEW.filled_quantity = 0.006 THEN
          PERFORM pg_sleep(0.2);
        END IF;
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;
      DROP TRIGGER IF EXISTS delay_high_fill ON "${schema}".orders;
      CREATE TRIGGER delay_high_fill
      BEFORE UPDATE ON "${schema}".orders
      FOR EACH ROW EXECUTE FUNCTION "${schema}".delay_high_fill();
    `);
  });

  it('serializes overlapping accepts and rejects the stale terminal transition', async () => {
    const newerFill = service.acceptOrderUpdate(createUpdate({}));
    await new Promise((resolve) => setTimeout(resolve, 25));
    const staleCancellation = service.acceptOrderUpdate(
      createUpdate({
        update_time: '2026-03-21T20:05:00Z',
        status: 'cancelled',
        filled_quantity: '0.004',
        average_fill_price: '45000',
        error_message: 'stale cancellation',
      }),
    );

    await Promise.all([newerFill, staleCancellation]);

    await expect(
      database.getRepository(OrderEntity).findOneByOrFail({
        venue: 'USD_M',
        clientOrderId: 'main-1',
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        exchangeOrderId: 'exchange-789',
        status: 'PARTIALLY_FILLED',
        filledQuantity: '0.00600000',
        averageFillPrice: '45005.00000000',
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      }),
    );
  });

  it('rejects adjacent NUMERIC(18,8) prices as conflicting identity', async () => {
    await database.query(
      `UPDATE "${schema}".orders SET price = $1 WHERE client_order_id = 'main-1'`,
      ['9999999999.00000001'],
    );

    await expect(
      service.acceptOrderUpdate(
        createUpdate({
          price: '9999999999.00000002',
          filled_quantity: '0.00000000',
          average_fill_price: null,
        }),
      ),
    ).resolves.toBeNull();

    await expect(
      database.query(
        `SELECT price::text AS price FROM "${schema}".orders WHERE client_order_id = 'main-1'`,
      ),
    ).resolves.toEqual([{ price: '9999999999.00000001' }]);
  });

  it('preserves exact stored decimals during a status-only update', async () => {
    await database.query(
      `
          UPDATE "${schema}".orders
          SET price = $1,
              quantity = $2,
              filled_quantity = $3,
              average_fill_price = $4,
              status = 'PARTIALLY_FILLED',
              last_update_time = $5
          WHERE client_order_id = 'main-1'
        `,
      [
        '9999999999.00000001',
        '1.00000000',
        '0.12345678',
        '9999999999.00000001',
        '2026-03-21T20:05:00Z',
      ],
    );

    await service.acceptOrderUpdate(
      createUpdate({
        update_time: '2026-03-21T20:06:00Z',
        status: 'cancelled',
        quantity: '1.00000000',
        price: '9999999999.00000001',
        filled_quantity: '0.12345678',
        average_fill_price: '9999999999.00000001',
      }),
    );

    await expect(
      database.query(
        `
          SELECT
            price::text AS price,
            filled_quantity::text AS filled_quantity,
            average_fill_price::text AS average_fill_price,
            status
          FROM "${schema}".orders
          WHERE client_order_id = 'main-1'
        `,
      ),
    ).resolves.toEqual([
      {
        price: '9999999999.00000001',
        filled_quantity: '0.12345678',
        average_fill_price: '9999999999.00000001',
        status: 'CANCELED',
      },
    ]);
  });

  it('accepts an exchange fill older than a synthetic placement acknowledgement', async () => {
    await database.query(
      `
        UPDATE "${schema}".orders
        SET exchange_order_id = NULL,
            last_update_time = NULL
        WHERE client_order_id = 'main-1'
      `,
    );

    await service.acceptOrderUpdate(
      createUpdate({
        order_id: '',
        update_time: '2026-03-21T20:06:00Z',
        status: 'new',
        filled_quantity: '0',
        average_fill_price: null,
      }),
    );
    await service.acceptOrderUpdate(
      createUpdate({
        order_id: 'exchange-789',
        update_time: '2026-03-21T20:05:00Z',
        status: 'filled',
        filled_quantity: '0.01',
        average_fill_price: '45001',
      }),
    );

    await expect(
      database.getRepository(OrderEntity).findOneByOrFail({
        venue: 'USD_M',
        clientOrderId: 'main-1',
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        exchangeOrderId: 'exchange-789',
        status: 'FILLED',
        filledQuantity: '0.01000000',
        averageFillPrice: '45001.00000000',
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      }),
    );
  });

  it('acknowledges a synthetic placement replay without mutating a partial fill', async () => {
    await database.query(
      `
        UPDATE "${schema}".orders
        SET status = 'PARTIALLY_FILLED',
            filled_quantity = 0.006,
            average_fill_price = 45005,
            last_update_time = '2026-03-21T20:06:00Z'
        WHERE client_order_id = 'main-1'
      `,
    );

    await expect(
      service.acceptOrderUpdate(
        createUpdate({
          order_id: '',
          update_time: '2026-03-21T20:07:00Z',
          status: 'new',
          filled_quantity: '0',
          average_fill_price: null,
        }),
      ),
    ).resolves.toEqual(
      expect.objectContaining({
        status: 'PARTIALLY_FILLED',
        executedQty: 0.006,
        executedPrice: 45005,
        timestamp: Date.parse('2026-03-21T20:06:00Z'),
      }),
    );

    await expect(
      database.getRepository(OrderEntity).findOneByOrFail({
        venue: 'USD_M',
        clientOrderId: 'main-1',
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        exchangeOrderId: 'exchange-789',
        status: 'PARTIALLY_FILLED',
        filledQuantity: '0.00600000',
        averageFillPrice: '45005.00000000',
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      }),
    );
  });

  it.each([
    ['PARTIALLY_FILLED', 'partially_filled', '0.50000000'],
    ['FILLED', 'filled', '1.00000000'],
  ] as const)(
    'persists a newer same-quantity average-fill correction for %s',
    async (persistedStatus, incomingStatus, filledQuantity) => {
      await database.query(
        `
          UPDATE "${schema}".orders
          SET status = $1,
              quantity = 1,
              filled_quantity = $2,
              average_fill_price = 45005,
              last_update_time = '2026-03-21T20:05:00Z'
          WHERE client_order_id = 'main-1'
        `,
        [persistedStatus, filledQuantity],
      );

      await service.acceptOrderUpdate(
        createUpdate({
          update_time: '2026-03-21T20:06:00Z',
          status: incomingStatus,
          quantity: '1.00000000',
          filled_quantity: filledQuantity,
          average_fill_price: '45010.00000000',
        }),
      );

      await expect(
        database.getRepository(OrderEntity).findOneByOrFail({
          venue: 'USD_M',
          clientOrderId: 'main-1',
        }),
      ).resolves.toEqual(
        expect.objectContaining({
          status: persistedStatus,
          filledQuantity,
          averageFillPrice: '45010.00000000',
          lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
        }),
      );
    },
  );

  it('rebuilds the cached position after a terminal average correction', async () => {
    await database.query(
      `UPDATE "${schema}".orders SET quantity = 1 WHERE client_order_id = 'main-1'`,
    );
    await database.query(
      `
        INSERT INTO "${schema}".positions (
          venue, symbol, side, size, entry_price, current_price,
          unrealized_pnl, updated_at, is_active
        ) VALUES ('USD_M', 'BTCUSDT', 'BUY', 1, 45005, 45005, 0,
                  '2026-03-21T20:05:00Z', TRUE)
      `,
    );
    await service.acceptOrderUpdate(
      createUpdate({
        update_time: '2026-03-21T20:05:00Z',
        status: 'filled',
        quantity: '1.00000000',
        filled_quantity: '1.00000000',
        average_fill_price: '45005.00000000',
      }),
    );
    await expect(
      database.getRepository(OrderEntity).findOneByOrFail({
        venue: 'USD_M',
        clientOrderId: 'main-1',
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        status: 'FILLED',
        filledQuantity: '1.00000000',
        averageFillPrice: '45005.00000000',
      }),
    );
    await expect(service.getPositions()).resolves.toEqual([
      expect.objectContaining({
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        quantity: 1,
        entryPrice: 45005,
        currentPrice: 45005,
      }),
    ]);

    await database.query(
      `
        UPDATE "${schema}".positions
        SET entry_price = 45010,
            current_price = 45010,
            updated_at = '2026-03-21T20:06:00Z'
        WHERE venue = 'USD_M' AND symbol = 'BTCUSDT' AND is_active = TRUE
      `,
    );
    await service.acceptOrderUpdate(
      createUpdate({
        update_time: '2026-03-21T20:06:00Z',
        status: 'filled',
        quantity: '1.00000000',
        filled_quantity: '1.00000000',
        average_fill_price: '45010.00000000',
      }),
    );

    await expect(service.getPositions()).resolves.toEqual([
      expect.objectContaining({
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        quantity: 1,
        entryPrice: 45010,
        currentPrice: 45010,
      }),
    ]);
    const [row] = await database.query(
      `SELECT average_fill_price::text FROM "${schema}".orders WHERE client_order_id = 'main-1'`,
    );
    expect(row).toEqual(
      expect.objectContaining({
        average_fill_price: '45010.00000000',
      }),
    );
  });

  it('restores the authoritative position snapshot without replaying cumulative orders', async () => {
    await database.query(
      `
        INSERT INTO "${schema}".positions (
          venue, symbol, side, size, entry_price, current_price,
          unrealized_pnl, updated_at, is_active
        ) VALUES ('USD_M', 'BTCUSDT', 'BUY', 5, 112.5, 112.5, 0,
                  '2026-03-21T20:03:00Z', TRUE)
      `,
    );

    await service.onModuleInit();

    await expect(service.getPositions()).resolves.toEqual([
      expect.objectContaining({
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: 5,
        entryPrice: 112.5,
        currentPrice: 112.5,
      }),
    ]);
  });

  it.each([
    ['cancellation then fill', ['cancelled', 'filled']],
    ['fill then cancellation', ['filled', 'cancelled']],
  ] as const)('resolves equal-timestamp %s deterministically', async (_name, arrivalOrder) => {
    for (const status of arrivalOrder) {
      await service.acceptOrderUpdate(
        createUpdate(
          status === 'filled'
            ? {
                status,
                filled_quantity: '0.01',
                average_fill_price: '45001',
              }
            : {
                status,
                filled_quantity: '0.004',
                average_fill_price: '45000',
                error_message: 'exchange cancellation',
              },
        ),
      );
    }

    await expect(
      database.getRepository(OrderEntity).findOneByOrFail({
        venue: 'USD_M',
        clientOrderId: 'main-1',
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        status: 'FILLED',
        filledQuantity: '0.01000000',
        averageFillPrice: '45001.00000000',
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
        rejectReason: null,
      }),
    );
  });

  it('scopes exchange identifier ownership to one venue and symbol', async () => {
    const repository = database.getRepository(OrderEntity);
    await repository.save({
      orderId: randomUUID(),
      clientOrderId: 'other-main',
      exchangeOrderId: 'exchange-other',
      decisionId: '22222222-2222-4222-8222-222222222222',
      venue: 'USD_M',
      symbol: 'ETHUSDT',
      side: 'SELL',
      type: 'LIMIT',
      quantity: 0.02,
      price: 3500,
      stopPrice: null,
      timeInForce: 'GTC',
      status: 'NEW',
      filledQuantity: 0,
      averageFillPrice: null,
      lastUpdateTime: null,
      commission: 0,
      commissionAsset: null,
      reduceOnly: false,
      postOnly: false,
      closePosition: false,
      activationPrice: null,
      callbackRate: null,
      workingType: null,
      priceProtect: false,
      rejectReason: null,
    });
    await database.query(
      `
        UPDATE "${schema}".orders
        SET exchange_order_id = NULL,
            last_update_time = NULL
        WHERE client_order_id = 'main-1'
      `,
    );

    await expect(
      service.acceptOrderUpdate(
        createUpdate({
          order_id: 'exchange-other',
          status: 'new',
          filled_quantity: '0',
          average_fill_price: null,
        }),
      ),
    ).resolves.toEqual(expect.objectContaining({ orderId: expect.any(String), status: 'NEW' }));

    await expect(
      repository.findOneByOrFail({ venue: 'USD_M', clientOrderId: 'main-1' }),
    ).resolves.toEqual(
      expect.objectContaining({ exchangeOrderId: 'exchange-other', status: 'NEW' }),
    );
    await expect(
      repository.findOneByOrFail({ venue: 'USD_M', clientOrderId: 'other-main' }),
    ).resolves.toEqual(
      expect.objectContaining({ exchangeOrderId: 'exchange-other', status: 'NEW' }),
    );

    await expect(
      repository.save({
        orderId: randomUUID(),
        clientOrderId: 'same-symbol-owner',
        exchangeOrderId: 'exchange-other',
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        status: 'NEW',
        filledQuantity: 0,
        createdAt: new Date(),
      }),
    ).rejects.toMatchObject({ code: '23505' });
  });
});
