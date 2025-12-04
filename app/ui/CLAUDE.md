# Next.js Trading UI

**Technology**: TypeScript | Next.js 14+ | React | Lightweight Charts
**Entry Point**: `src/app/layout.tsx`
**Parent Context**: This extends [../../CLAUDE.md](../../CLAUDE.md)

---

## Development Commands

### This Package

```bash
# From app/ui directory
pnpm dev                     # Start dev server (port 3000)
pnpm build                   # Build for production
pnpm start                   # Start production server
pnpm test                    # Run Vitest
pnpm test:watch              # Watch mode
pnpm lint                    # ESLint
pnpm lint:fix                # Auto-fix
pnpm typecheck               # Type checking
```

### From Root

```bash
make dev-ui                  # Start with hot reload
make test-ui                 # Run vitest
make lint                    # Lint all
make typecheck               # Type check all
pnpm --filter @repo/ui dev
```

### Pre-PR Checklist

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

---

## Architecture

### Directory Structure

```
app/ui/src/
├── app/                       # Next.js App Router
│   ├── layout.tsx            # Root layout
│   ├── page.tsx              # Home page
│   ├── dashboard/            # Dashboard routes
│   │   ├── layout.tsx
│   │   └── page.tsx
│   └── trading/              # Trading routes
│       ├── layout.tsx
│       └── [symbol]/
│           └── page.tsx
├── components/                # React components
│   ├── charts/               # Trading charts
│   │   ├── Chart.tsx         # Main chart component
│   │   ├── IndicatorPanel.tsx
│   │   └── SmcOverlays.tsx   # SMC visualizations
│   ├── common/               # Shared components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── Modal.tsx
│   ├── layout/               # Layout components
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── Footer.tsx
│   ├── trading/              # Trading components
│   │   ├── OrderForm.tsx
│   │   ├── OrderBook.tsx
│   │   └── PositionTable.tsx
│   ├── alerts/               # Alert components
│   └── Dashboard/            # Dashboard components
├── config/                    # Configuration
│   └── constants.ts
├── constants/                 # App constants
├── context/                   # React context
│   ├── AuthContext.tsx
│   └── ThemeContext.tsx
├── hooks/                     # Custom hooks
│   ├── useWebSocket.ts
│   ├── useOrders.ts
│   └── useMarketData.ts
├── services/                  # API services
│   ├── api.ts                # Base API client
│   ├── orders.ts             # Order API
│   └── websocket.ts          # WebSocket client
├── styles/                    # Global styles
│   └── globals.css
├── types/                     # TypeScript types
│   ├── order.ts
│   ├── candle.ts
│   └── index.ts
└── utils/                     # Utility functions
    ├── formatting.ts
    ├── validation.ts
    └── helpers.ts
```

### Code Organization Patterns

#### Component Structure

```tsx
// ✅ DO: Use functional components with TypeScript
type OrderFormProps = {
  symbol: string;
  onSubmit: (order: OrderRequest) => void;
};

export function OrderForm({ symbol, onSubmit }: OrderFormProps) {
  const [quantity, setQuantity] = useState('');
  const [side, setSide] = useState<OrderSide>('BUY');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({ symbol, quantity, side });
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form content */}
    </form>
  );
}
```

#### Custom Hooks

```tsx
// ✅ DO: Extract reusable logic into hooks
export function useOrders(symbol: string) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetchOrders(symbol)
      .then(setOrders)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [symbol]);

  return { orders, loading, error };
}
```

#### WebSocket Integration

```tsx
// ✅ DO: Use WebSocket hook for real-time data
export function useWebSocket(url: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      setMessages((prev) => [...prev, JSON.parse(event.data)]);
    };

    return () => socket.close();
  }, [url]);

  const send = useCallback((data: unknown) => {
    socketRef.current?.send(JSON.stringify(data));
  }, []);

  return { messages, send };
}
```

#### Chart Integration

```tsx
// ✅ DO: Use Lightweight Charts properly
import { createChart, IChartApi } from 'lightweight-charts';

export function Chart({ candles }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 400,
    });

    chartRef.current = chart;
    const candleSeries = chart.addCandlestickSeries();
    candleSeries.setData(candles);

    return () => chart.remove();
  }, [candles]);

  return <div ref={containerRef} />;
}
```

---

## Key Files

### Core Files (understand these first)

- `src/app/layout.tsx` - Root layout, providers
- `src/app/page.tsx` - Home page
- `src/services/api.ts` - Base API client
- `src/services/websocket.ts` - WebSocket client

### Components

- `src/components/charts/Chart.tsx` - Main trading chart
- `src/components/charts/SmcOverlays.tsx` - SMC visualizations
- `src/components/trading/OrderForm.tsx` - Order entry form
- `src/components/trading/PositionTable.tsx` - Open positions

### Hooks

- `src/hooks/useWebSocket.ts` - WebSocket connection
- `src/hooks/useOrders.ts` - Order management
- `src/hooks/useMarketData.ts` - Real-time market data

### Types

- `src/types/order.ts` - Order types
- `src/types/candle.ts` - Candle/OHLCV types
- `src/types/index.ts` - Re-exports

---

## Quick Search Commands

### Find Components

```bash
# Find component definitions
rg -n "^export function " app/ui/src/components/

# Find component usage
rg -n "<OrderForm" app/ui/src/

# Find props interfaces
rg -n "type.*Props" app/ui/src/components/
```

### Find Hooks

```bash
# Find custom hooks
rg -n "^export function use" app/ui/src/hooks/

# Find hook usage
rg -n "use[A-Z].*\(" app/ui/src/
```

### Find Routes

```bash
# Find page components (App Router)
fd -g "page.tsx" app/ui/src/app/

# Find layouts
fd -g "layout.tsx" app/ui/src/app/

# Find API routes
fd -g "route.ts" app/ui/src/app/api/
```

### Find Tests

```bash
# Find test files
fd -g "*.spec.ts" app/ui/
fd -g "*.spec.tsx" app/ui/

# Find specific component tests
rg -n "describe\(" app/ui/src/components/
```

---

## Common Gotchas

- **Server Components**: Default in Next.js 13+, add `"use client"` only when needed
- **Dynamic Routes**: Params are async in Next.js 15+ - use `await params`
- **Environment Variables**: Client-side vars need `NEXT_PUBLIC_` prefix
- **Absolute Imports**: Use `@/` prefix for imports from `src/`
- **Chart Rendering**: Lightweight Charts needs DOM - use `useEffect`
- **WebSocket Cleanup**: Always close WebSocket in `useEffect` cleanup
- **Decimal Display**: Format prices with proper precision using `toFixed()`

---

## Testing Guidelines

### Unit Tests

- Location: Colocated (`*.spec.tsx`) or `tests/unit/`
- Framework: Vitest + Testing Library

```tsx
// ✅ DO: Test user interactions
import { render, screen, fireEvent } from '@testing-library/react';
import { OrderForm } from './OrderForm';

describe('OrderForm', () => {
  it('submits order with correct values', async () => {
    const onSubmit = vi.fn();
    render(<OrderForm symbol="BTCUSDT" onSubmit={onSubmit} />);

    await fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '0.001' },
    });
    await fireEvent.click(screen.getByRole('button', { name: /buy/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      symbol: 'BTCUSDT',
      quantity: '0.001',
      side: 'BUY',
    });
  });
});
```

### E2E Tests

- Location: `tests/e2e/`
- Framework: Playwright

```typescript
// ✅ DO: Test critical user flows
import { test, expect } from '@playwright/test';

test('user can submit a market order', async ({ page }) => {
  await page.goto('/trading/BTCUSDT');

  await page.fill('[data-testid="quantity-input"]', '0.001');
  await page.click('[data-testid="buy-button"]');

  await expect(page.locator('[data-testid="order-success"]')).toBeVisible();
});
```

### Running Tests

```bash
# Unit tests
pnpm test

# Watch mode
pnpm test:watch

# Coverage
pnpm test:coverage

# E2E tests
pnpm playwright test

# Specific component
pnpm test OrderForm
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

## Performance Targets

| Metric | Target |
|--------|--------|
| Chart redraw | <150ms |
| WebSocket latency | <100ms |
| Page load (LCP) | <2.5s |
| First Input Delay | <100ms |

---

## Styling

- **Framework**: Tailwind CSS
- **Design Tokens**: Use tokens from `src/styles/tokens.ts`
- **Dark Mode**: Supported via `dark:` prefix

```tsx
// ✅ DO: Use Tailwind classes
<button className="bg-primary text-white px-4 py-2 rounded hover:bg-primary-dark">
  Buy
</button>

// ❌ DON'T: Hardcode colors
<button className="bg-blue-500">
  Buy
</button>
```
