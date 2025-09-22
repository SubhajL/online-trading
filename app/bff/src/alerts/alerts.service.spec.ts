import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AlertsService } from './alerts.service';
import { Alert } from './entities/alert.entity';
import { NotFoundException } from '@nestjs/common';
import type { AlertFilters } from './dto/alert.dto';

describe('AlertsService', () => {
  let service: AlertsService;
  let repository: Repository<Alert>;

  const mockRepository = {
    findAndCount: jest.fn(),
    findOne: jest.fn(),
    save: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
    count: jest.fn(),
    createQueryBuilder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AlertsService,
        {
          provide: getRepositoryToken(Alert),
          useValue: mockRepository,
        },
      ],
    }).compile();

    service = module.get<AlertsService>(AlertsService);
    repository = module.get<Repository<Alert>>(getRepositoryToken(Alert));
    jest.clearAllMocks();
  });

  const mockAlert: Alert = {
    id: 'alert-123',
    type: 'order',
    priority: 'high',
    title: 'Order Filled',
    message: 'Your order has been filled',
    data: { orderId: 'order-456' },
    read: false,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  describe('findAll', () => {
    it('should return paginated alerts', async () => {
      mockRepository.findAndCount.mockResolvedValue([[mockAlert], 1]);

      const result = await service.findAll(1, 20, {});

      expect(result).toEqual({
        data: [mockAlert],
        total: 1,
        page: 1,
        limit: 20,
      });
      expect(repository.findAndCount).toHaveBeenCalledWith({
        where: {},
        take: 20,
        skip: 0,
        order: { createdAt: 'DESC' },
      });
    });

    it('should apply filters', async () => {
      const filters: AlertFilters = {
        type: 'order',
        priority: 'high',
        read: false,
      };
      mockRepository.findAndCount.mockResolvedValue([[mockAlert], 1]);

      await service.findAll(1, 20, filters);

      expect(repository.findAndCount).toHaveBeenCalledWith({
        where: {
          type: 'order',
          priority: 'high',
          read: false,
        },
        take: 20,
        skip: 0,
        order: { createdAt: 'DESC' },
      });
    });
  });

  describe('findOne', () => {
    it('should return single alert', async () => {
      mockRepository.findOne.mockResolvedValue(mockAlert);

      const result = await service.findOne('alert-123');

      expect(result).toEqual(mockAlert);
      expect(repository.findOne).toHaveBeenCalledWith({ where: { id: 'alert-123' } });
    });

    it('should throw NotFoundException if not found', async () => {
      mockRepository.findOne.mockResolvedValue(null);

      await expect(service.findOne('invalid-id')).rejects.toThrow(NotFoundException);
    });
  });

  describe('markAsRead', () => {
    it('should mark alert as read', async () => {
      const updatedAlert = { ...mockAlert, read: true };
      mockRepository.findOne.mockResolvedValue(mockAlert);
      mockRepository.save.mockResolvedValue(updatedAlert);

      const result = await service.markAsRead('alert-123');

      expect(result.read).toBe(true);
      expect(repository.save).toHaveBeenCalledWith({ ...mockAlert, read: true });
    });

    it('should throw NotFoundException if alert not found', async () => {
      mockRepository.findOne.mockResolvedValue(null);

      await expect(service.markAsRead('invalid-id')).rejects.toThrow(NotFoundException);
    });
  });

  describe('markAllAsRead', () => {
    it('should mark all unread alerts as read', async () => {
      mockRepository.update.mockResolvedValue({ affected: 5 });

      const result = await service.markAllAsRead();

      expect(result).toEqual({ updated: 5 });
      expect(repository.update).toHaveBeenCalledWith({ read: false }, { read: true });
    });
  });

  describe('delete', () => {
    it('should delete alert', async () => {
      mockRepository.findOne.mockResolvedValue(mockAlert);
      mockRepository.delete.mockResolvedValue({ affected: 1 });

      await service.delete('alert-123');

      expect(repository.delete).toHaveBeenCalledWith('alert-123');
    });

    it('should throw NotFoundException if alert not found', async () => {
      mockRepository.findOne.mockResolvedValue(null);

      await expect(service.delete('invalid-id')).rejects.toThrow(NotFoundException);
    });
  });

  describe('getStats', () => {
    it('should return alert statistics', async () => {
      const mockQueryBuilder = {
        select: jest.fn().mockReturnThis(),
        addSelect: jest.fn().mockReturnThis(),
        groupBy: jest.fn().mockReturnThis(),
        getRawMany: jest.fn().mockResolvedValue([
          { type: 'order', count: '10' },
          { type: 'position', count: '5' },
        ]),
        getRawOne: jest.fn().mockResolvedValue({ total: '100', unread: '25' }),
      };
      mockRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await service.getStats();

      expect(result).toHaveProperty('total');
      expect(result).toHaveProperty('unread');
      expect(result).toHaveProperty('byType');
      expect(result).toHaveProperty('byPriority');
    });
  });

  describe('getUnreadCount', () => {
    it('should return unread count', async () => {
      mockRepository.count.mockResolvedValue(5);

      const result = await service.getUnreadCount();

      expect(result).toEqual({ count: 5 });
      expect(repository.count).toHaveBeenCalledWith({ where: { read: false } });
    });
  });

  describe('search', () => {
    it('should search alerts by query', async () => {
      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        orWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getManyAndCount: jest.fn().mockResolvedValue([[mockAlert], 1]),
      };
      mockRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await service.search('BTC', 50);

      expect(result).toEqual({
        data: [mockAlert],
        total: 1,
      });
      expect(repository.createQueryBuilder).toHaveBeenCalled();
    });
  });

  describe('export', () => {
    it('should export alerts as CSV', async () => {
      mockRepository.findAndCount.mockResolvedValue([[mockAlert], 1]);

      const result = await service.export('csv', {});

      expect(result).toBeInstanceOf(Buffer);
      // CSV should contain headers and data
      const csvString = result.toString();
      expect(csvString).toContain('id,type,priority,title,message,read,createdAt');
    });

    it('should export alerts as JSON', async () => {
      mockRepository.findAndCount.mockResolvedValue([[mockAlert], 1]);

      const result = await service.export('json', {});

      expect(result).toBeInstanceOf(Buffer);
      const jsonData = JSON.parse(result.toString());
      expect(jsonData).toHaveProperty('alerts');
      expect(jsonData.alerts).toHaveLength(1);
    });
  });

  describe('create', () => {
    it('should create new alert', async () => {
      const newAlert = {
        type: 'order' as const,
        priority: 'high' as const,
        title: 'New Order',
        message: 'Order placed',
        data: { orderId: '123' },
      };
      mockRepository.save.mockResolvedValue({ ...newAlert, id: 'new-alert', read: false, createdAt: new Date() });

      const result = await service.create(newAlert);

      expect(result).toHaveProperty('id');
      expect(repository.save).toHaveBeenCalledWith(expect.objectContaining(newAlert));
    });
  });
});