import { Test, TestingModule } from '@nestjs/testing';
import { AppModule } from './app.module';
import { ConfigModule } from './config/config.module';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
import { MarketDataModule } from './market-data/market-data.module';
import { TradingModule } from './trading/trading.module';
import { EventEmitterModule } from '@nestjs/event-emitter';

describe('AppModule', () => {
  let module: TestingModule;

  beforeEach(async () => {
    module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
  });

  it('should be defined', () => {
    expect(module).toBeDefined();
  });

  it('should import ConfigModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasConfigModule = imports.some((importedModule: any) => {
      return (
        importedModule === ConfigModule ||
        importedModule.module === ConfigModule ||
        importedModule.name === 'ConfigModule'
      );
    });
    expect(hasConfigModule).toBe(true);
  });

  it('should import EventEmitterModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasEventEmitterModule = imports.some((importedModule: any) => {
      return (
        importedModule === EventEmitterModule ||
        importedModule.module === EventEmitterModule ||
        importedModule.name === 'EventEmitterModule'
      );
    });
    expect(hasEventEmitterModule).toBe(true);
  });

  it('should import HealthModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasHealthModule = imports.some((importedModule: any) => {
      return importedModule === HealthModule;
    });
    expect(hasHealthModule).toBe(true);
  });

  it('should import EngineClientModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasEngineClientModule = imports.some((importedModule: any) => {
      return importedModule === EngineClientModule;
    });
    expect(hasEngineClientModule).toBe(true);
  });

  it('should import RouterClientModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasRouterClientModule = imports.some((importedModule: any) => {
      return importedModule === RouterClientModule;
    });
    expect(hasRouterClientModule).toBe(true);
  });

  it('should import MarketDataModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasMarketDataModule = imports.some((importedModule: any) => {
      return importedModule === MarketDataModule;
    });
    expect(hasMarketDataModule).toBe(true);
  });

  it('should import TradingModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasTradingModule = imports.some((importedModule: any) => {
      return importedModule === TradingModule;
    });
    expect(hasTradingModule).toBe(true);
  });
});
