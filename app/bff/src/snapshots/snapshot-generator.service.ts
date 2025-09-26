import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { SignalPayloadDto } from '../alerts/dto/signal-payload.dto';
import * as puppeteer from 'puppeteer';

@Injectable()
export class SnapshotGeneratorService implements OnModuleDestroy {
  private readonly logger = new Logger(SnapshotGeneratorService.name);
  private browser: puppeteer.Browser | null = null;
  private useCount = 0;
  private readonly maxUseCount = 20;
  private readonly baseUrl: string;
  private readonly executablePath: string | undefined;

  constructor(private readonly configService: ConfigService) {
    this.baseUrl = this.configService.get<string>('APP_BASE_URL', 'http://localhost:3000');
    this.executablePath = this.configService.get<string>('PUPPETEER_EXECUTABLE_PATH');
  }

  async generateSnapshot(signal: SignalPayloadDto): Promise<Buffer> {
    await this.ensureBrowser();

    const page = await this.browser!.newPage();

    try {
      // Build render URL
      const url = this.buildRenderUrl(signal);

      // Navigate to snapshot render page
      await page.goto(url, { waitUntil: 'networkidle2' });

      // Set viewport
      await page.setViewport({
        width: 1200,
        height: 628,
        deviceScaleFactor: 1.5,
      });

      // Wait for chart to be ready
      await page.waitForFunction('window.__SNAPSHOT_READY__ === true', {
        timeout: 10000,
      });

      // Take screenshot
      const screenshot = await page.screenshot({
        type: 'png',
        fullPage: false,
      });

      await page.close();

      // Increment use count and recycle if needed
      this.useCount++;
      if (this.useCount >= this.maxUseCount) {
        await this.recycleBrowser();
      }

      return Buffer.from(screenshot);
    } catch (error) {
      await page.close();
      this.logger.error(`Failed to generate snapshot: ${error}`);
      throw new Error('Failed to generate snapshot');
    }
  }

  private buildRenderUrl(signal: SignalPayloadDto): string {
    const params = new URLSearchParams({
      symbol: signal.symbol,
      timeframe: signal.timeframe,
      side: signal.side,
      entry: signal.entry.toString(),
      stopLoss: signal.stopLoss.toString(),
      takeProfit: signal.takeProfit.toString(),
      signalTime: signal.signalTime,
    });

    if (signal.reasons && signal.reasons.length > 0) {
      params.append('reasons', signal.reasons.join(','));
    }

    if (signal.context) {
      if (signal.context.preCandles) {
        params.append('preCandles', signal.context.preCandles.toString());
      }
      if (signal.context.postCandles) {
        params.append('postCandles', signal.context.postCandles.toString());
      }
    }

    return `${this.baseUrl}/snapshots/${signal.signalId}/render?${params.toString()}`;
  }

  private async ensureBrowser(): Promise<void> {
    if (!this.browser) {
      this.browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        executablePath: this.executablePath,
      });
      this.logger.log('Puppeteer browser launched');
    }
  }

  private async recycleBrowser(): Promise<void> {
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
      this.useCount = 0;
      this.logger.log('Browser recycled after maximum uses');
    }
  }

  async onModuleDestroy(): Promise<void> {
    if (this.browser) {
      await this.browser.close();
      this.logger.log('Browser closed on module destroy');
    }
  }
}
