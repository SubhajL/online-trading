import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { SnapshotGeneratorService } from './snapshot-generator.service';
import { SignalPayloadDto, SignalSide } from '../alerts/dto/signal-payload.dto';
import * as puppeteer from 'puppeteer';

jest.mock('puppeteer');

describe('SnapshotGeneratorService', () => {
  let service: SnapshotGeneratorService;
  let mockBrowser: any;
  let mockPage: any;

  beforeEach(async () => {
    mockPage = {
      goto: jest.fn(),
      setViewport: jest.fn(),
      waitForFunction: jest.fn(),
      screenshot: jest.fn(),
      close: jest.fn(),
    };

    mockBrowser = {
      newPage: jest.fn().mockResolvedValue(mockPage),
      close: jest.fn(),
    };

    (puppeteer.launch as jest.Mock).mockResolvedValue(mockBrowser);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SnapshotGeneratorService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config: Record<string, any> = {
                APP_BASE_URL: 'http://localhost:3000',
                PUPPETEER_EXECUTABLE_PATH: undefined,
              };
              return config[key];
            }),
          },
        },
      ],
    }).compile();

    service = module.get<SnapshotGeneratorService>(SnapshotGeneratorService);
  });

  afterEach(async () => {
    await service.onModuleDestroy();
    jest.clearAllMocks();
  });

  describe('generateSnapshot', () => {
    const testSignal: SignalPayloadDto = {
      signalId: 'test-123',
      symbol: 'BTCUSDT',
      timeframe: '15m',
      side: SignalSide.BUY,
      entry: 52000,
      stopLoss: 51000,
      takeProfit: 53000,
      signalTime: '2025-01-26T10:00:00Z',
      reasons: ['SMC Breaker', 'BOS'],
      context: { preCandles: 100, postCandles: 20 },
    };

    it('returns PNG buffer for valid signal', async () => {
      const fakeImageBuffer = Buffer.from('fake-png-data');
      mockPage.screenshot.mockResolvedValue(fakeImageBuffer);

      const result = await service.generateSnapshot(testSignal);

      expect(result).toStrictEqual(fakeImageBuffer);
      expect(result.length).toBeGreaterThan(0);
    });

    it('sets correct viewport dimensions', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      await service.generateSnapshot(testSignal);

      expect(mockPage.setViewport).toHaveBeenCalledWith({
        width: 1200,
        height: 628,
        deviceScaleFactor: 1.5,
      });
    });

    it('waits for SNAPSHOT_READY flag', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      await service.generateSnapshot(testSignal);

      expect(mockPage.waitForFunction).toHaveBeenCalledWith('window.__SNAPSHOT_READY__ === true', {
        timeout: 10000,
      });
    });

    it('recycles browser after 20 uses', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      // Generate 20 snapshots
      for (let i = 0; i < 20; i++) {
        await service.generateSnapshot(testSignal);
      }

      // 21st should trigger browser recycle
      await service.generateSnapshot(testSignal);

      expect(mockBrowser.close).toHaveBeenCalledTimes(1);
      expect(puppeteer.launch).toHaveBeenCalledTimes(2); // Initial + recycle
    });

    it('handles page crash gracefully', async () => {
      mockPage.goto.mockRejectedValue(new Error('Page crashed'));

      await expect(service.generateSnapshot(testSignal)).rejects.toThrow(
        'Failed to generate snapshot',
      );

      // Should close page even on error
      expect(mockPage.close).toHaveBeenCalled();
    });

    it('builds correct render URL with all parameters', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      await service.generateSnapshot(testSignal);

      expect(mockPage.goto).toHaveBeenCalledWith(
        expect.stringContaining('/snapshots/test-123/render'),
        { waitUntil: 'networkidle2' },
      );

      const calledUrl = mockPage.goto.mock.calls[0][0];
      expect(calledUrl).toContain('symbol=BTCUSDT');
      expect(calledUrl).toContain('timeframe=15m');
      expect(calledUrl).toContain('side=BUY');
      expect(calledUrl).toContain('entry=52000');
      expect(calledUrl).toContain('stopLoss=51000');
      expect(calledUrl).toContain('takeProfit=53000');
      expect(calledUrl).toContain('signalTime=2025-01-26T10%3A00%3A00Z');
      expect(calledUrl).toContain('reasons=SMC+Breaker%2CBOS');
      expect(calledUrl).toContain('preCandles=100');
      expect(calledUrl).toContain('postCandles=20');
    });
  });

  describe('browser pool management', () => {
    it('initializes browser pool on first use', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      await service.generateSnapshot({
        signalId: 'test',
        symbol: 'BTCUSDT',
        timeframe: '15m',
        side: SignalSide.BUY,
        entry: 50000,
        stopLoss: 49000,
        takeProfit: 51000,
        signalTime: '2025-01-26T10:00:00Z',
      });

      expect(puppeteer.launch).toHaveBeenCalledWith({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        executablePath: undefined,
      });
    });

    it('reuses browser for multiple snapshots', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      // Generate multiple snapshots
      for (let i = 0; i < 5; i++) {
        await service.generateSnapshot({
          signalId: `test-${i}`,
          symbol: 'BTCUSDT',
          timeframe: '15m',
          side: SignalSide.BUY,
          entry: 50000,
          stopLoss: 49000,
          takeProfit: 51000,
          signalTime: '2025-01-26T10:00:00Z',
        });
      }

      // Browser should be launched only once
      expect(puppeteer.launch).toHaveBeenCalledTimes(1);
      // New page for each snapshot
      expect(mockBrowser.newPage).toHaveBeenCalledTimes(5);
    });

    it('closes browser on module destroy', async () => {
      mockPage.screenshot.mockResolvedValue(Buffer.from('png'));

      // Generate a snapshot to initialize browser
      await service.generateSnapshot({
        signalId: 'test',
        symbol: 'BTCUSDT',
        timeframe: '15m',
        side: SignalSide.BUY,
        entry: 50000,
        stopLoss: 49000,
        takeProfit: 51000,
        signalTime: '2025-01-26T10:00:00Z',
      });

      await service.onModuleDestroy();

      expect(mockBrowser.close).toHaveBeenCalled();
    });
  });
});
