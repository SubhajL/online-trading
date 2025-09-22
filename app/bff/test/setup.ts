// Mock TypeORM to avoid database connections during unit tests
jest.mock('typeorm', () => ({
  ...jest.requireActual('typeorm'),
  DataSource: jest.fn().mockImplementation(() => ({
    initialize: jest.fn().mockResolvedValue(true),
    destroy: jest.fn().mockResolvedValue(true),
    getRepository: jest.fn(),
  })),
  Entity: jest.fn(),
  Column: jest.fn(),
  PrimaryColumn: jest.fn(),
  Index: jest.fn(),
  CreateDateColumn: jest.fn(),
  UpdateDateColumn: jest.fn(),
  PrimaryGeneratedColumn: jest.fn(),
  ManyToOne: jest.fn(),
  JoinColumn: jest.fn(),
}));

// Mock ConfigService for database module
jest.mock('@nestjs/config', () => ({
  ...jest.requireActual('@nestjs/config'),
  ConfigService: jest.fn().mockImplementation(() => ({
    get: jest.fn((key: string) => {
      const config: Record<string, any> = {
        'database.host': 'localhost',
        'database.port': 5432,
        'database.username': 'test',
        'database.password': 'test',
        'database.database': 'test',
      };
      return config[key];
    }),
  })),
}));
