import { Test, TestingModule } from '@nestjs/testing';
import { DataSource } from 'typeorm';
import { DatabaseSchemaVerifierService } from './database-schema-verifier.service';

describe('DatabaseSchemaVerifierService', () => {
  const mockDataSource = {
    query: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('passes when alerts tables are present', async () => {
    mockDataSource.query.mockResolvedValue([
      {
        alerts: 'alerts',
        alert_snapshots: 'alert_snapshots',
      },
    ]);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        DatabaseSchemaVerifierService,
        {
          provide: DataSource,
          useValue: mockDataSource,
        },
      ],
    }).compile();

    const service = module.get<DatabaseSchemaVerifierService>(DatabaseSchemaVerifierService);

    await expect(service.onModuleInit()).resolves.toBeUndefined();
  });

  it('fails closed when required alert tables are missing', async () => {
    mockDataSource.query.mockResolvedValue([
      {
        alerts: null,
        alert_snapshots: null,
      },
    ]);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        DatabaseSchemaVerifierService,
        {
          provide: DataSource,
          useValue: mockDataSource,
        },
      ],
    }).compile();

    const service = module.get<DatabaseSchemaVerifierService>(DatabaseSchemaVerifierService);

    await expect(service.onModuleInit()).rejects.toThrow(
      'Missing required BFF database tables: alerts, alert_snapshots',
    );
  });
});
