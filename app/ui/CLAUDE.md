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

## Authoritative Design References

- **MUST** follow [guidelines/COMPREHENSIVE_UX_UI_GUIDELINES.md](../../guidelines/COMPREHENSIVE_UX_UI_GUIDELINES.md) — Nielsen heuristics, Gestalt principles, IA, interaction design
- **MUST** follow [guidelines/COMPREHENSIVE_STYLE_GUIDELINES.md](../../guidelines/COMPREHENSIVE_STYLE_GUIDELINES.md) — tokens, component standards, responsive grid, motion
- **MUST** follow [guidelines/FRONTEND_REBUILD_WIREFRAMES_AND_V0_PROMPTS.md](../../guidelines/FRONTEND_REBUILD_WIREFRAMES_AND_V0_PROMPTS.md) — wireframes (G0-G4, P0-P6), v0.dev prompts

---

## Component Library & Accessibility

### shadcn/ui + Radix (MUST)

- **MUST** use shadcn/ui primitives for all generic UI components (`components/ui/`)
- **MUST NOT** hand-build primitives that shadcn provides: Button, Dialog, Popover, DropdownMenu, Select, Command, Tabs, Toast (Sonner), Tooltip, ScrollArea, Table, Badge, Skeleton, Switch, Input, Resizable
- **MUST** keep trading-domain components custom: chart panels, order forms, position displays, SMC overlays, equity curves, emergency controls
- **MUST** override shadcn defaults with project design tokens — never use shadcn's default colors

### Accessibility (MUST)

- **MUST** include `eslint-plugin-jsx-a11y` in the ESLint config — violations are lint errors, not warnings
- **MUST** add an axe-core assertion in every Playwright route test:
  ```ts
  import AxeBuilder from '@axe-core/playwright';
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  ```
- **MUST** meet WCAG 2.1 AA contrast ratios: 4.5:1 for text, 3:1 for UI elements (Style Guide §7)
- **MUST** ensure keyboard navigation works end-to-end on every route (Tab, Escape, Enter, Arrow keys)
- **MUST** never use color as the only indicator — add icons or text labels (Style Guide §7)
- **MUST** support `prefers-reduced-motion` media query for all animations (Style Guide §8)
- **SHOULD** use semantic HTML elements (`<nav>`, `<main>`, `<section>`, `<form>`) over generic `<div>`

### Interactive Component States (MUST — Style Guide §6, UX Guide Component Checklist)

Every interactive component **MUST** handle these 7 states:

| # | State | Description |
|---|-------|-------------|
| 1 | **Default** | Rest state |
| 2 | **Hover** | Mouse over — subtle color/shadow change (Style Guide §8) |
| 3 | **Active** | Being clicked — scale or opacity feedback |
| 4 | **Focus** | Keyboard navigation — `2px solid primary-500, 2px offset` (UX Guide) |
| 5 | **Disabled** | Not available — reduced opacity, no shadow |
| 6 | **Loading** | Processing — skeleton or spinner |
| 7 | **Error** | Invalid state — error color border + message |

### Data Component States (MUST)

Every data-displaying component **MUST** handle all applicable states:

| # | State | Description |
|---|-------|-------------|
| 1 | **Empty** | No data yet (first load, empty portfolio) |
| 2 | **Loading** | Data is being fetched (skeleton/spinner) |
| 3 | **Partial** | Some data loaded, more coming (streaming) |
| 4 | **Full** | Normal state with complete data |
| 5 | **Error** | Fetch failed, WS disconnected, invalid input |
| 6 | **Offline** | Network unavailable, stale data displayed |
| 7 | **Overflow** | Unexpectedly large data (100+ positions, long text) |

### Error Messages (MUST — UX Guide, Nielsen #9)

All error messages **MUST** follow the 3-part formula:
1. **What happened** (plain language, not technical)
2. **Why it happened** (if relevant to the user)
3. **How to fix it** (actionable next step)

```tsx
// ❌ DON'T: "Error: ECONNRESET"
// ✅ DO: "Connection lost. The server is not responding. Reconnecting automatically..."
```

### Storybook (MUST for new components)

- **MUST** create a Storybook story for every new component in `components/ui/` and `components/trading/`
- **MUST** include story variants for all applicable states
- **SHOULD** use Storybook for visual verification before wiring into pages

### Lighthouse CI (MUST)

- **MUST** maintain Lighthouse CI performance budgets in CI pipeline
- **MUST** fail CI if any route exceeds: LCP > 2.5s, CLS > 0.1, FID > 100ms

---

## Styling & Design Tokens

- **Framework**: Tailwind CSS
- **Design Tokens**: Single source of truth in `src/styles/tokens.css` mapped via `tailwind.config.ts`
- **Dark Mode**: Supported via `dark:` prefix
- **Authoritative token reference**: [guidelines/COMPREHENSIVE_STYLE_GUIDELINES.md §5](../../guidelines/COMPREHENSIVE_STYLE_GUIDELINES.md)

### Token Architecture

```
src/styles/tokens.css          → CSS custom properties (colors, spacing, typography, motion, shadows, radii)
tailwind.config.ts             → Maps CSS tokens to Tailwind utility classes
components/ui/                 → shadcn components consume Tailwind tokens
components/trading/            → Domain components consume Tailwind tokens
```

### Color Tokens (Style Guide §4.1, §5 — 60-30-10 Rule)

```css
--color-primary: #6C5CE7;       /* Primary buttons, active states, key highlights */
--color-primary-dark: #5936E0;   /* Hover/pressed state */
--color-secondary: #4B5563;      /* Secondary actions, text on dark surfaces */
--color-accent: #14B8A6;         /* Links, subtle highlights, data viz accents */
--color-surface: #111827;        /* Primary text / dark bg (neutral-900) */
--color-surface-raised: #1F2937; /* Cards, panels */
--color-neutral-100: #F9FAFB;   /* Backgrounds, panels */
--color-neutral-300: #D1D5DB;   /* Borders, dividers */
--color-neutral-500: #9CA3AF;   /* Disabled text, secondary labels */
--color-success: #22C55E;        /* PnL positive, success states */
--color-error: #EF4444;          /* PnL negative, errors */
--color-warning: #F59E0B;        /* Risk alerts, warnings */
```

### Spacing (8px grid — Style Guide §5, §9)

```css
--space-xs: 4px;   --space-sm: 8px;   --space-md: 16px;
--space-lg: 24px;  --space-xl: 32px;  --space-2xl: 48px;
```

Spacing hierarchy: Macro (64px+) → Section (32-48px) → Element (16-24px) → Micro (4-12px)

### Typography (Inter, Major Third 1.250 — Style Guide §4.2)

```css
--font-size-xs: 12.8px;  --font-size-sm: 14px;  --font-size-base: 16px;
--font-size-lg: 20px;    --font-size-xl: 25px;   --font-size-2xl: 31.25px;
```

### Border Radius, Shadows, Motion (Style Guide §5, §8)

```css
/* Radius */
--radius-sm: 4px;  --radius-md: 8px;  --radius-lg: 16px;  --radius-pill: 999px;

/* Shadows */
--shadow-sm: 0 1px 3px rgba(0,0,0,0.12);
--shadow-md: 0 4px 8px rgba(0,0,0,0.10);
--shadow-lg: 0 8px 16px rgba(0,0,0,0.10);

/* Motion — MUST use tokens, never hardcode durations */
--anim-fast: 150ms ease;    /* Hover effects, color transitions */
--anim-medium: 250ms ease;  /* Modal enter/exit, panel transitions */
--anim-slow: 400ms ease;    /* Page transitions, complex animations */
```

- **MUST** support `prefers-reduced-motion` (disable transforms/transitions)

### Usage Rules

```tsx
// ✅ DO: Use Tailwind classes mapped to tokens
<button className="bg-primary text-white px-4 py-2 rounded-sm hover:bg-primary-dark transition-colors duration-150">
  Buy
</button>

// ❌ DON'T: Hardcode colors or durations
<button className="bg-blue-500" style={{ transition: '200ms' }}>
  Buy
</button>
```

---

## Responsive Grid System (Style Guide §9)

| Breakpoint | Width | Grid | Layout |
|---|---|---|---|
| `sm` (mobile) | ≤767px | 4-column | Single column, full-width, hamburger menu |
| `md` (tablet) | 768-1023px | 8-column | Stack complex layouts |
| `lg` (desktop) | 1024-1279px | 12-column | Two-column layouts |
| `xl` (wide) | ≥1280px | 12-column | Max content width 1200px centered |

- **MUST** use Tailwind responsive prefixes (`sm:`, `md:`, `lg:`, `xl:`)
- **MUST** maintain consistent gutters (16-24px) across breakpoints
- **MUST** ensure touch targets ≥44px on touch devices (Style Guide §6.1)

---

## Alerts & Toasts (Style Guide §6.4)

- Icon (20px) + message, 12px/16px padding, 4px radius, colored `border-left`
- Auto-dismiss 5-7s for low/medium; persist for high/critical
- Stack vertically with 8px gap; desktop top-right, mobile bottom

## Modals (Style Guide §6.3)

- Backdrop `rgba(0,0,0,0.5)`, lock scroll, 16px radius, `--shadow-lg`, 24px padding
- Animation: fade + 4% scale using `--anim-medium`
- Max-width ~600px desktop, 90vw mobile

## Power User (UX Guide, Nielsen #7)

- **MUST** implement Command Palette (shadcn Command, `Ctrl+K`)

---

## Component Folder Structure (Target)

```
src/components/
├── ui/                  # shadcn primitives (Button, Dialog, Select, etc.)
├── trading/             # Domain: order form, positions, balances
├── charts/              # Domain: candlestick, indicators, overlays
├── dashboard/           # Domain: KPIs, guards, equity curve
├── layout/              # Shell: sidebar, header, panels, resizable
├── alerts/              # Alert components
└── common/              # ErrorBoundary, SkipLink, LoadingSpinner
```
