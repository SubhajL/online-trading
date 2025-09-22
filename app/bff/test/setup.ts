// Mock TypeORM to avoid database connections during unit tests
jest.mock('typeorm', () => {
  const actual = jest.requireActual('typeorm');
  return {
    ...actual,
    DataSource: jest.fn().mockImplementation(() => ({
      initialize: jest.fn().mockResolvedValue(true),
      destroy: jest.fn().mockResolvedValue(true),
      getRepository: jest.fn(),
    })),
    Entity: () => (target: any) => target,
    Column: () => (target: any, key: string) => {},
    PrimaryColumn: () => (target: any, key: string) => {},
    Index: () => (target: any) => target,
    CreateDateColumn: () => (target: any, key: string) => {},
    UpdateDateColumn: () => (target: any, key: string) => {},
    PrimaryGeneratedColumn: () => (target: any, key: string) => {},
    ManyToOne: () => (target: any, key: string) => {},
    JoinColumn: () => (target: any, key: string) => {},
    OneToMany: () => (target: any, key: string) => {},
  };
});

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
