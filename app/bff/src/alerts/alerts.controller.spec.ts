import { Test, TestingModule } from '@nestjs/testing';
import { AlertsController } from './alerts.controller';
import { AlertsService } from './alerts.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import type { Alert, AlertFilters } from './dto/alert.dto';

describe('AlertsController', () => {
  let controller: AlertsController;
  let service: AlertsService;

  const mockAlertsService = {
    findAll: jest.fn(),
    findOne: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
    delete: jest.fn(),
    getStats: jest.fn(),
    getUnreadCount: jest.fn(),
    search: jest.fn(),
    export: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [AlertsController],
      providers: [
        {
          provide: AlertsService,
          useValue: mockAlertsService,
        },
      ],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get<AlertsController>(AlertsController);
    service = module.get<AlertsService>(AlertsService);
    jest.clearAllMocks();
  });

  const mockAlert: Alert = {
    id: 'alert-123',
    type: 'order',
    priority: 'high',
    title: 'Order Filled',
    message: 'Your BTC order has been filled',
    data: { orderId: 'order-456', symbol: 'BTCUSDT' },
    read: false,
    createdAt: new Date().toISOString(),
  };

  describe('GET /api/alerts', () => {
    it('should return paginated alerts', async () => {
      const mockResponse = {
        data: [mockAlert],
        total: 1,
        page: 1,
        limit: 20,
      };
      mockAlertsService.findAll.mockResolvedValue(mockResponse);

      const result = await controller.findAll(1, 20, {});

      expect(result).toEqual(mockResponse);
      expect(service.findAll).toHaveBeenCalledWith(1, 20, {});
    });

    it('should apply filters when provided', async () => {
      const filters: AlertFilters = {
        type: 'order',
        priority: 'high',
        read: false,
      };
      const mockResponse = {
        data: [mockAlert],
        total: 1,
        page: 1,
        limit: 20,
      };
      mockAlertsService.findAll.mockResolvedValue(mockResponse);

      await controller.findAll(1, 20, filters);

      expect(service.findAll).toHaveBeenCalledWith(1, 20, filters);
    });
  });

  describe('GET /api/alerts/:id', () => {
    it('should return single alert', async () => {
      mockAlertsService.findOne.mockResolvedValue(mockAlert);

      const result = await controller.findOne('alert-123');

      expect(result).toEqual(mockAlert);
      expect(service.findOne).toHaveBeenCalledWith('alert-123');
    });

    it('should handle not found error', async () => {
      mockAlertsService.findOne.mockRejectedValue(new Error('Alert not found'));

      await expect(controller.findOne('invalid-id')).rejects.toThrow('Alert not found');
    });
  });

  describe('PUT /api/alerts/:id/read', () => {
    it('should mark alert as read', async () => {
      const updatedAlert = { ...mockAlert, read: true };
      mockAlertsService.markAsRead.mockResolvedValue(updatedAlert);

      const result = await controller.markAsRead('alert-123');

      expect(result).toEqual(updatedAlert);
      expect(service.markAsRead).toHaveBeenCalledWith('alert-123');
    });
  });

  describe('PUT /api/alerts/read-all', () => {
    it('should mark all alerts as read', async () => {
      const response = { updated: 5 };
      mockAlertsService.markAllAsRead.mockResolvedValue(response);

      const result = await controller.markAllAsRead();

      expect(result).toEqual(response);
      expect(service.markAllAsRead).toHaveBeenCalled();
    });
  });

  describe('DELETE /api/alerts/:id', () => {
    it('should delete alert', async () => {
      mockAlertsService.delete.mockResolvedValue(undefined);

      await controller.delete('alert-123');

      expect(service.delete).toHaveBeenCalledWith('alert-123');
    });
  });

  describe('GET /api/alerts/stats', () => {
    it('should return alert statistics', async () => {
      const mockStats = {
        total: 100,
        unread: 25,
        byType: { order: 30, position: 20, decision: 15, smc: 20, error: 10, info: 5 },
        byPriority: { low: 40, medium: 30, high: 20, critical: 10 },
      };
      mockAlertsService.getStats.mockResolvedValue(mockStats);

      const result = await controller.getStats();

      expect(result).toEqual(mockStats);
      expect(service.getStats).toHaveBeenCalled();
    });
  });

  describe('GET /api/alerts/unread-count', () => {
    it('should return unread count', async () => {
      const response = { count: 5 };
      mockAlertsService.getUnreadCount.mockResolvedValue(response);

      const result = await controller.getUnreadCount();

      expect(result).toEqual(response);
      expect(service.getUnreadCount).toHaveBeenCalled();
    });
  });

  describe('GET /api/alerts/search', () => {
    it('should search alerts', async () => {
      const mockResults = {
        data: [mockAlert],
        total: 1,
      };
      mockAlertsService.search.mockResolvedValue(mockResults);

      const result = await controller.search('BTC');

      expect(result).toEqual(mockResults);
      expect(service.search).toHaveBeenCalledWith('BTC', 50);
    });

    it('should use custom limit', async () => {
      mockAlertsService.search.mockResolvedValue({ data: [], total: 0 });

      await controller.search('ETH', 10);

      expect(service.search).toHaveBeenCalledWith('ETH', 10);
    });
  });

  describe('GET /api/alerts/export', () => {
    it('should export alerts as CSV', async () => {
      const mockBlob = Buffer.from('csv data');
      mockAlertsService.export.mockResolvedValue(mockBlob);

      const res = {
        set: jest.fn(),
        send: jest.fn(),
      };

      await controller.export('csv', {}, res as any);

      expect(service.export).toHaveBeenCalledWith('csv', {});
      expect(res.set).toHaveBeenCalledWith({
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename="alerts.csv"',
      });
      expect(res.send).toHaveBeenCalledWith(mockBlob);
    });

    it('should export alerts as JSON', async () => {
      const mockBlob = Buffer.from('json data');
      mockAlertsService.export.mockResolvedValue(mockBlob);

      const res = {
        set: jest.fn(),
        send: jest.fn(),
      };

      await controller.export('json', {}, res as any);

      expect(res.set).toHaveBeenCalledWith({
        'Content-Type': 'application/json',
        'Content-Disposition': 'attachment; filename="alerts.json"',
      });
    });
  });
});