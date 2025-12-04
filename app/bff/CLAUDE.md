# NestJS Backend-for-Frontend

**Technology**: TypeScript | NestJS | TypeORM | WebSocket
**Entry Point**: `src/main.ts`
**Parent Context**: This extends [../../CLAUDE.md](../../CLAUDE.md)

---

## Development Commands

### This Package

```bash
# From app/bff directory
pnpm dev                    # Start with hot reload
pnpm build                  # Build for production
pnpm test                   # Run Jest tests
pnpm test:watch             # Watch mode
pnpm test:cov               # With coverage
pnpm lint                   # ESLint
pnpm lint:fix               # Auto-fix
pnpm typecheck              # Type checking
```

### From Root

```bash
make dev-bff                # Start with hot reload (nest start --watch)
make test-bff               # Run jest
make lint                   # Lint all
make typecheck              # Type check all
pnpm --filter @repo/bff test
```

### Pre-PR Checklist

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

---

## Architecture

### Directory Structure

```
app/bff/src/
├── alerts/                    # Alert management
│   ├── alerts.module.ts
│   ├── alerts.service.ts
│   └── alerts.controller.ts
├── auth/                      # Authentication
│   ├── auth.module.ts
│   ├── auth.service.ts
│   ├── auth.guard.ts
│   └── jwt.strategy.ts
├── balances/                  # Account balances
│   └── balances.service.ts
├── config/                    # Configuration
│   └── configuration.ts
├── database/                  # TypeORM setup
│   └── database.module.ts
├── engine-client/             # Engine API client
│   ├── engine-client.module.ts
│   └── engine-client.service.ts
├── health/                    # Health checks
│   ├── health.module.ts
│   └── health.controller.ts
├── market-data/               # Market data
│   ├── market-data.module.ts
│   └── market-data.service.ts
├── orders/                    # Order management
│   ├── orders.module.ts
│   ├── orders.service.ts
│   └── orders.controller.ts
├── router-client/             # Router API client
│   └── router-client.service.ts
├── snapshots/                 # State snapshots
│   └── snapshots.service.ts
├── trading/                   # Trading logic
│   ├── trading.module.ts
│   └── trading.service.ts
├── websockets/                # WebSocket gateway
│   ├── websocket.module.ts
│   └── websocket.gateway.ts
├── app.module.ts              # Root module
└── main.ts                    # Bootstrap
```

### Code Organization Patterns

#### Module Structure

```typescript
// ✅ DO: Keep modules focused
@Module({
  imports: [DatabaseModule, ConfigModule],
  providers: [OrdersService],
  controllers: [OrdersController],
  exports: [OrdersService],
})
export class OrdersModule {}
```

#### Service Pattern

```typescript
// ✅ DO: Use dependency injection
@Injectable()
export class OrdersService {
  constructor(
    @InjectRepository(Order)
    private readonly orderRepository: Repository<Order>,
    private readonly routerClient: RouterClientService,
    private readonly logger: Logger,
  ) {}

  async submitOrder(dto: CreateOrderDto): Promise<Order> {
    // Validate
    // Submit to router
    // Persist to database
  }
}
```

#### DTO Validation

```typescript
// ✅ DO: Use class-validator for DTOs
export class CreateOrderDto {
  @IsString()
  @IsNotEmpty()
  symbol: string;

  @IsEnum(OrderSide)
  side: OrderSide;

  @IsDecimal()
  @IsPositive()
  quantity: string;

  @IsOptional()
  @IsDecimal()
  price?: string;
}
```

#### WebSocket Gateway

```typescript
// ✅ DO: Use proper decorators
@WebSocketGateway({
  namespace: '/trading',
  cors: { origin: '*' },
})
export class TradingGateway implements OnGatewayInit, OnGatewayConnection {
  @WebSocketServer()
  server: Server;

  @SubscribeMessage('subscribe')
  handleSubscribe(client: Socket, payload: SubscribeDto): void {
    // Handle subscription
  }

  broadcastUpdate(event: string, data: unknown): void {
    this.server.emit(event, data);
  }
}
```

#### Error Handling

```typescript
// ✅ DO: Use NestJS exception filters
@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const status = exception.getStatus();

    response.status(status).json({
      statusCode: status,
      message: exception.message,
      timestamp: new Date().toISOString(),
    });
  }
}
```

---

## Key Files

### Core Files (understand these first)

- `src/main.ts` - Bootstrap, global pipes, CORS, prefix
- `src/app.module.ts` - Root module, imports all features
- `src/config/configuration.ts` - Environment configuration

### API Layer

- `src/orders/orders.controller.ts` - Order REST endpoints
- `src/health/health.controller.ts` - Health/ready/live probes
- `src/websockets/websocket.gateway.ts` - Real-time updates

### Service Layer

- `src/orders/orders.service.ts` - Order business logic
- `src/engine-client/engine-client.service.ts` - Engine API calls
- `src/router-client/router-client.service.ts` - Router API calls

### Data Layer

- `src/database/database.module.ts` - TypeORM configuration
- `src/*/entities/*.entity.ts` - TypeORM entities

---

## Quick Search Commands

### Find Components

```bash
# Find controllers
rg -n "@Controller" app/bff/src/

# Find services
rg -n "@Injectable" app/bff/src/

# Find modules
rg -n "@Module" app/bff/src/

# Find WebSocket handlers
rg -n "@SubscribeMessage" app/bff/src/
```

### Find Tests

```bash
# Find all test files
fd -g "*.spec.ts" app/bff/

# Find tests for a module
rg -n "describe\(" app/bff/src/orders/

# Run specific test
pnpm test -- --testPathPattern="orders.service"
```

### Find Routes

```bash
# Find REST endpoints
rg -n "@(Get|Post|Put|Delete|Patch)\(" app/bff/src/

# Find route paths
rg -n "@Controller\(" app/bff/src/
```

---

## Common Gotchas

- **Validation Pipe**: Global pipe is configured - all DTOs are auto-validated
- **CORS**: Configured in `main.ts`, update for production
- **Global Prefix**: All routes prefixed with `/api`
- **WebSocket Namespace**: Use `/trading` namespace for WS connections
- **TypeORM Sync**: NEVER use `synchronize: true` in production
- **Decimal Precision**: Use strings for prices, parse with `Decimal.js`
- **Environment**: Use `ConfigService` not `process.env` directly

---

## Testing Guidelines

### Unit Tests

- Location: Colocated (`*.spec.ts`)
- Framework: Jest + NestJS testing utilities

```typescript
// ✅ DO: Use NestJS testing module
describe('OrdersService', () => {
  let service: OrdersService;
  let mockRepository: MockType<Repository<Order>>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        OrdersService,
        {
          provide: getRepositoryToken(Order),
          useFactory: repositoryMockFactory,
        },
      ],
    }).compile();

    service = module.get<OrdersService>(OrdersService);
  });

  it('should create an order', async () => {
    // Test implementation
  });
});
```

### Integration Tests

- Location: `test/integration/`
- Require: Running database

```typescript
// ✅ DO: Use e2e testing for API endpoints
describe('Orders API (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  it('/orders (POST)', () => {
    return request(app.getHttpServer())
      .post('/api/orders')
      .send({ symbol: 'BTCUSDT', side: 'BUY', quantity: '0.001' })
      .expect(201);
  });
});
```

### Running Tests

```bash
# Unit tests
pnpm test

# Watch mode
pnpm test:watch

# Coverage
pnpm test:cov

# E2E tests
pnpm test:e2e

# Specific file
pnpm test -- orders.service.spec.ts
```

---

## Pre-PR Checklist

Run this before creating a PR:

```bash
# All must pass
pnpm typecheck && \
pnpm lint && \
pnpm test && \
pnpm build
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/health/live` | Liveness probe |
| GET | `/api/health/ready` | Readiness probe |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Submit order |
| GET | `/api/orders/:id` | Get order by ID |
| DELETE | `/api/orders/:id` | Cancel order |
| GET | `/api/balances` | Account balances |
| GET | `/api/positions` | Open positions |
| WS | `/trading` | Real-time updates |
