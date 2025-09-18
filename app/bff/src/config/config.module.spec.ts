import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { ConfigModule } from './config.module';

describe('ConfigModule', () => {
  let configService: ConfigService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      imports: [ConfigModule.forRoot()],
    }).compile();

    configService = module.get<ConfigService>(ConfigService);
  });

  it('should be defined', () => {
    expect(configService).toBeDefined();
  });

  it('provides configuration through ConfigService', () => {
    expect(configService.get('nodeEnv')).toBeDefined();
    expect(configService.get('port')).toBeDefined();
    expect(configService.get('engine')).toBeDefined();
    expect(configService.get('router')).toBeDefined();
    expect(configService.get('websocket')).toBeDefined();
  });

  it('allows nested configuration access', () => {
    expect(configService.get('engine.host')).toBeDefined();
    expect(configService.get('router.url')).toBeDefined();
    expect(configService.get('websocket.namespace')).toBeDefined();
  });

  it('returns typed configuration values', () => {
    const port = configService.get<number>('port');
    const engineType = configService.get<'redis' | 'tcp'>('engine.type');

    expect(typeof port).toBe('number');
    expect(['redis', 'tcp']).toContain(engineType);
  });

  it('is globally available', () => {
    const moduleExports = ConfigModule.forRoot();
    expect(moduleExports.global).toBe(true);
  });
});
