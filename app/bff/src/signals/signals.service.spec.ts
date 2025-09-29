import { Test, TestingModule } from '@nestjs/testing';
import { getQueueToken } from '@nestjs/bull';
import { NotFoundException } from '@nestjs/common';
import { SignalsService } from './signals.service';
import { AlertsService } from '../alerts/alerts.service';
import { SnapshotsService } from '../snapshots/snapshots.service';
import { CreateSignalAlertDto } from './dto/create-signal-alert.dto';
import { Venue } from '../balances/dto/get-balances.dto';
import { Alert } from '../alerts/entities/alert.entity';
import { Queue } from 'bull';

describe('SignalsService', () => {
  let service: SignalsService;
  let alertsService: AlertsService;
  let snapshotsService: SnapshotsService;
  let signalQueue: Queue;

  const mockAlertsService = {
    create: jest.fn(),
    findByData: jest.fn(),
  };

  const mockSnapshotsService = {
    findBySignalId: jest.fn(),
  };

  const mockSignalQueue = {
    add: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SignalsService,
        {
          provide: AlertsService,
          useValue: mockAlertsService,
        },
        {
          provide: SnapshotsService,
          useValue: mockSnapshotsService,
        },
        {
          provide: getQueueToken('signal-alerts'),
          useValue: mockSignalQueue,
        },
      ],
    }).compile();

    service = module.get<SignalsService>(SignalsService);
    alertsService = module.get<AlertsService>(AlertsService);
    snapshotsService = module.get<SnapshotsService>(SnapshotsService);
    signalQueue = module.get<Queue>(getQueueToken('signal-alerts'));
  });

  describe('createAlert', () => {
    const createSignalAlertDto: CreateSignalAlertDto = {
      signalId: 'signal-123',
      symbol: 'BTCUSDT',
      venue: Venue.USD_M,
      side: 'BUY',
      entry: 45000,
      stopLoss: 44000,
      takeProfit: 46000,
      confidence: 0.85,
      reasons: ['SMC confluence', 'Strong support retest'],
      timeframe: '1h',
      signalTime: new Date().toISOString(),
    };

    it('should queue alert and persist via AlertsService', async () => {
      mockAlertsService.findByData.mockResolvedValue(null);
      mockAlertsService.create.mockResolvedValue({
        id: 'alert-456',
        type: 'smc',
        priority: 'high',
        title: 'Signal: BUY BTCUSDT',
        message: 'Trading signal for BTCUSDT - BUY at 45000',
        data: createSignalAlertDto,
        read: false,
        createdAt: new Date(),
        updatedAt: new Date(),
      });

      const result = await service.createAlert(createSignalAlertDto);

      expect(mockAlertsService.findByData).toHaveBeenCalledWith({
        signalId: createSignalAlertDto.signalId,
      });
      expect(mockSignalQueue.add).toHaveBeenCalledWith('process-signal', createSignalAlertDto);
      expect(mockAlertsService.create).toHaveBeenCalledWith({
        type: 'smc',
        priority: 'high',
        title: 'Signal: BUY BTCUSDT',
        message: 'Trading signal for BTCUSDT - BUY at 45000',
        data: createSignalAlertDto,
      });
      expect(result).toEqual({
        signalId: createSignalAlertDto.signalId,
        success: true,
        message: 'Signal alert queued for processing',
      });
    });

    it('should handle duplicate signals with idempotency', async () => {
      const existingAlert: Alert = {
        id: 'alert-existing',
        type: 'smc',
        priority: 'high',
        title: 'Signal: BUY BTCUSDT',
        message: 'Trading signal for BTCUSDT - BUY at 45000',
        data: createSignalAlertDto,
        read: false,
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      mockAlertsService.findByData.mockResolvedValue(existingAlert);

      const result = await service.createAlert(createSignalAlertDto);

      expect(mockAlertsService.findByData).toHaveBeenCalledWith({
        signalId: createSignalAlertDto.signalId,
      });
      expect(mockSignalQueue.add).not.toHaveBeenCalled();
      expect(mockAlertsService.create).not.toHaveBeenCalled();
      expect(result).toEqual({
        signalId: createSignalAlertDto.signalId,
        success: true,
        message: 'Signal alert already exists',
      });
    });

    it('should transform signal data correctly for alert creation', async () => {
      mockAlertsService.findByData.mockResolvedValue(null);
      mockAlertsService.create.mockResolvedValue({} as Alert);

      const dto: CreateSignalAlertDto = {
        ...createSignalAlertDto,
        side: 'SELL',
        entry: 50000,
      };

      await service.createAlert(dto);

      expect(mockAlertsService.create).toHaveBeenCalledWith({
        type: 'smc',
        priority: 'high',
        title: 'Signal: SELL BTCUSDT',
        message: 'Trading signal for BTCUSDT - SELL at 50000',
        data: dto,
      });
    });

    it('should propagate downstream service errors', async () => {
      mockAlertsService.findByData.mockRejectedValue(new Error('Database error'));

      await expect(service.createAlert(createSignalAlertDto)).rejects.toThrow('Database error');
    });
  });

  describe('getSnapshot', () => {
    it('should retrieve snapshot by signal ID', async () => {
      const mockSnapshot = {
        id: 'snapshot-123',
        signalId: 'signal-123',
        chartData: 'base64-encoded-image',
        metadata: { timeframe: '1h' },
        createdAt: new Date(),
      };

      mockSnapshotsService.findBySignalId.mockResolvedValue(mockSnapshot);

      const result = await service.getSnapshot('signal-123');

      expect(mockSnapshotsService.findBySignalId).toHaveBeenCalledWith('signal-123');
      expect(result).toEqual(mockSnapshot);
    });

    it('should throw NotFoundException when snapshot missing', async () => {
      mockSnapshotsService.findBySignalId.mockResolvedValue(null);

      await expect(service.getSnapshot('signal-404')).rejects.toThrow(NotFoundException);
      expect(mockSnapshotsService.findBySignalId).toHaveBeenCalledWith('signal-404');
    });
  });
});
