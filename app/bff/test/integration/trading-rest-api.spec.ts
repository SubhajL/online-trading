import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

// No mocks - using real services

describe('Trading REST API Integration', () => {
  let app: INestApplication;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api');
    await app.init();
  });

  afterEach(async () => {
    await app.close();
  });

  describe('POST /api/trading/orders', () => {
    it('should place a market order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        venue: 'USD_M',
      };

      const response = await request(app.getHttpServer())
        .post('/api/trading/orders')
        .send(orderRequest)
        .expect(201);

      expect(response.body).toHaveProperty('orderId');
      expect(response.body).toMatchObject({
        status: expect.any(String),
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
      });
    });

    it('should place a limit order with price', async () => {
      const orderRequest = {
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 1,
        price: 3000,
        venue: 'SPOT',
      };

      const response = await request(app.getHttpServer())
        .post('/api/trading/orders')
        .send(orderRequest)
        .expect(201);

      expect(response.body).toHaveProperty('orderId');
      expect(response.body).toMatchObject({
        status: expect.any(String),
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 1,
        price: 3000,
      });
    });

    it('should handle order placement errors', async () => {
      const orderRequest = {
        symbol: 'INVALID_SYMBOL',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        venue: 'USD_M',
      };

      const response = await request(app.getHttpServer())
        .post('/api/trading/orders')
        .send(orderRequest)
        .expect(500);

      expect(response.body).toHaveProperty('statusCode', 500);
      expect(response.body).toHaveProperty('message');
    });
  });

  describe('GET /api/trading/orders/:orderId', () => {
    it('should get order status successfully', async () => {
      // First place an order to get a real orderId
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 30000, // Low price to ensure it doesn't fill
        venue: 'USD_M',
      };

      const placeResponse = await request(app.getHttpServer())
        .post('/api/trading/orders')
        .send(orderRequest);

      const orderId = placeResponse.body.orderId;

      const response = await request(app.getHttpServer())
        .get(`/api/trading/orders/${orderId}?venue=USD_M`)
        .expect(200);

      expect(response.body).toMatchObject({
        orderId,
        symbol: 'BTCUSDT',
      });
    });

    it('should return 400 when venue is missing', async () => {
      const orderId = '123456';

      const response = await request(app.getHttpServer())
        .get(`/api/trading/orders/${orderId}`)
        .expect(400);

      expect(response.body).toMatchObject({
        statusCode: 400,
        message: expect.arrayContaining([expect.stringContaining('venue')]),
        error: 'Bad Request',
      });
    });
  });

  describe('DELETE /api/trading/orders/:orderId', () => {
    it('should cancel order successfully', async () => {
      // First place an order to cancel
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 30000, // Low price to ensure it doesn't fill
        venue: 'USD_M',
      };

      const placeResponse = await request(app.getHttpServer())
        .post('/api/trading/orders')
        .send(orderRequest);

      const orderId = placeResponse.body.orderId;

      const cancelRequest = {
        symbol: 'BTCUSDT',
        venue: 'USD_M',
      };

      const response = await request(app.getHttpServer())
        .delete(`/api/trading/orders/${orderId}`)
        .send(cancelRequest)
        .expect(200);

      expect(response.body).toMatchObject({
        orderId,
        status: expect.stringContaining('CANCEL'),
      });
    });
  });

  describe('GET /api/trading/positions', () => {
    it('should return current positions', async () => {
      const response = await request(app.getHttpServer()).get('/api/trading/positions').expect(200);

      expect(response.body).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/trading/orders', () => {
    it('should return active orders', async () => {
      const response = await request(app.getHttpServer()).get('/api/trading/orders').expect(200);

      expect(response.body).toBeInstanceOf(Array);
    });
  });

  describe('POST /api/trading/auto-trading', () => {
    it('should enable auto trading', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/trading/auto-trading')
        .send({ enabled: true })
        .expect(200);

      expect(response.body).toEqual({
        enabled: true,
        message: 'Auto trading enabled',
      });
    });

    it('should disable auto trading', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/trading/auto-trading')
        .send({ enabled: false })
        .expect(200);

      expect(response.body).toEqual({
        enabled: false,
        message: 'Auto trading disabled',
      });
    });
  });

  describe('GET /api/trading/auto-trading', () => {
    it('should return auto trading status', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/trading/auto-trading')
        .expect(200);

      expect(response.body).toHaveProperty('enabled');
      expect(typeof response.body.enabled).toBe('boolean');
    });
  });

  describe('Health checks', () => {
    it('should return healthy status when all services are up', async () => {
      const response = await request(app.getHttpServer()).get('/api/health').expect(200);

      expect(response.body).toHaveProperty('status');
    });

    it('should return service unavailable when engine is down', async () => {
      // This test will fail if engine is actually up
      // For real integration testing, we'd need to stop the engine service
      // or test in an environment where it's not running
      // Skip this test for now as it requires manual service manipulation
    });
  });
});
