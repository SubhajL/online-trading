import { Test, TestingModule } from '@nestjs/testing';
import { AppModule } from './app.module';
import { ConfigModule } from './config/config.module';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { DatabaseModule } from './database/database.module';
import { AuthModule } from './auth/auth.module';
import { BalancesModule } from './balances/balances.module';
import { OrdersModule } from './orders/orders.module';

describe('AppModule', () => {
  let module: TestingModule;

  beforeEach(async () => {
    module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
  }, 10000);

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

  it('should import DatabaseModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasDatabaseModule = imports.some((importedModule: any) => {
      return importedModule === DatabaseModule;
    });
    expect(hasDatabaseModule).toBe(true);
  });

  it('should import AuthModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasAuthModule = imports.some((importedModule: any) => {
      return importedModule === AuthModule;
    });
    expect(hasAuthModule).toBe(true);
  });

  it('should import BalancesModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasBalancesModule = imports.some((importedModule: any) => {
      return importedModule === BalancesModule;
    });
    expect(hasBalancesModule).toBe(true);
  });

  it('should import OrdersModule', () => {
    const imports = Reflect.getMetadata('imports', AppModule) || [];
    const hasOrdersModule = imports.some((importedModule: any) => {
      return importedModule === OrdersModule;
    });
    expect(hasOrdersModule).toBe(true);
  });
});
