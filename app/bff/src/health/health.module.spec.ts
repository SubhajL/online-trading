import { Test, TestingModule } from '@nestjs/testing';
import { HealthModule } from './health.module';
import { HealthController } from './health.controller';
import { TerminusModule } from '@nestjs/terminus';
import { ConfigModule } from '@nestjs/config';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { EventEmitterModule } from '@nestjs/event-emitter';

describe('HealthModule', () => {
  let module: TestingModule;

  beforeEach(async () => {
    module = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          load: [
            () => ({
              router: { url: 'http://localhost:8080' },
              engine: { host: 'localhost', port: 6379, type: 'redis' },
            }),
          ],
        }),
        EventEmitterModule.forRoot(),
        HealthModule,
      ],
    }).compile();
  });

  it('should be defined', () => {
    expect(module).toBeDefined();
  });

  it('should provide HealthController', () => {
    const controller = module.get<HealthController>(HealthController);
    expect(controller).toBeDefined();
  });

  it('should import TerminusModule', () => {
    const imports = Reflect.getMetadata('imports', HealthModule) || [];
    const hasTerminus = imports.some((importedModule: any) => {
      return importedModule === TerminusModule || importedModule.module === TerminusModule;
    });
    expect(hasTerminus).toBe(true);
  });

  it('should import EngineClientModule', () => {
    const imports = Reflect.getMetadata('imports', HealthModule) || [];
    const hasEngineClient = imports.some((importedModule: any) => {
      return importedModule === EngineClientModule;
    });
    expect(hasEngineClient).toBe(true);
  });

  it('should declare HealthController', () => {
    const controllers = Reflect.getMetadata('controllers', HealthModule) || [];
    expect(controllers).toContain(HealthController);
  });
});
