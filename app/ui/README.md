# Trading Platform UI

Next.js-based frontend for the trading platform with real-time market data visualization and trade execution.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS + CSS Custom Properties
- **Charts**: Lightweight Charts
- **Testing**: Vitest (unit) + Playwright (E2E)
- **Type Safety**: TypeScript with strict mode

## Getting Started

### Prerequisites

- Node.js 18+ and pnpm
- Trading platform backend running on port 8080

### Development

```bash
# Install dependencies
pnpm install

# Start dev server on port 3000
pnpm dev

# Run unit tests
pnpm test

# Run E2E tests
pnpm test:e2e

# Type checking
pnpm typecheck

# Linting
pnpm lint

# Format code
pnpm format
```

## Project Structure

```
src/
├── app/              # Next.js App Router pages
│   ├── page.tsx      # Dashboard (home)
│   ├── portfolio/    # Portfolio page
│   ├── trades/       # Active trades page
│   ├── history/      # Trade history page
│   ├── analytics/    # Analytics page
│   └── settings/     # Settings page
├── components/       # React components
│   ├── Layout/       # Header, Sidebar, etc.
│   ├── Dashboard/    # Dashboard-specific components
│   ├── Charts/       # Chart components
│   └── common/       # Reusable components
├── hooks/            # Custom React hooks
├── utils/            # Utility functions
├── styles/           # Global styles and design tokens
│   ├── globals.css   # Global styles
│   └── tokens.css    # Design token definitions
└── types/            # TypeScript type definitions

tests/
├── e2e/              # Playwright E2E tests
└── integration/      # Integration tests
```

## Design System

Our UI follows a comprehensive design system with centralized design tokens and custom Tailwind utilities.

### Documentation

- **[Design Tokens](./docs/design-tokens.md)** - Complete reference for colors, spacing, typography, and other design tokens
- **[Tailwind Custom Utilities](./docs/tailwind-custom-utilities.md)** - Guide to custom Tailwind configuration and utilities

### Key Features

- **Consistent Styling**: All styles use design tokens for easy theming
- **Accessibility**: WCAG AA compliant with 4.5:1 contrast ratios and 44px touch targets
- **Responsive**: Mobile-first design with consistent breakpoints
- **Type-Safe**: Full TypeScript coverage with strict mode

### Quick Reference

```tsx
// Using design tokens with Tailwind
;<div className="bg-surface-raised text-primary p-space-4 rounded-md">
  Content with consistent design tokens
</div>

// Navigation with active states
import { isPathActive, getNavLinkClassName } from '@/utils/navigation'

;<Link href="/dashboard" className={getNavLinkClassName(pathname, '/dashboard', 'nav-link')}>
  Dashboard
</Link>
```

## Testing

### Unit Tests (Vitest)

```bash
# Run all unit tests
pnpm test

# Watch mode
pnpm test:watch

# Coverage report
pnpm test:coverage
```

Unit tests are colocated with components:

- `Component.tsx` - Component implementation
- `Component.spec.tsx` - Unit tests

### E2E Tests (Playwright)

```bash
# Run all E2E tests
pnpm test:e2e

# Run specific test file
pnpm exec playwright test tests/e2e/navigation.spec.ts

# Run tests in headed mode (see browser)
pnpm exec playwright test --headed

# Update visual snapshots
pnpm exec playwright test --update-snapshots
```

E2E tests cover:

- Navigation accessibility (skip links, keyboard navigation)
- Active navigation states (Header & Sidebar)
- Visual regression testing
- Trading workflows
- Market data display

## API Integration

The UI communicates with the backend API at `http://localhost:8080`:

- `/api/v1/balances` - Account balances
- `/api/v1/positions` - Open positions
- `/api/v1/orders` - Order management
- WebSocket `/ws` - Real-time market data

## Environment Variables

Create `.env.local` for local development:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_WS_URL=ws://localhost:8080
```

## Accessibility

The UI is built with accessibility in mind:

- **Keyboard Navigation**: Full keyboard support with visible focus indicators
- **Skip Links**: Skip to main content links on all pages
- **ARIA Labels**: Proper ARIA labels for screen readers
- **Touch Targets**: Minimum 44px touch targets (WCAG AA)
- **Color Contrast**: 4.5:1 minimum contrast ratio (WCAG AA)
- **Semantic HTML**: Proper use of semantic elements

See [Design Tokens](./docs/design-tokens.md#wcag-compliance) for color contrast details.

## Performance

- **Code Splitting**: Automatic code splitting with Next.js App Router
- **Optimized Images**: Next.js Image component for optimized loading
- **Lazy Loading**: Components lazy loaded where appropriate
- **Chart Optimization**: Lightweight Charts library for fast rendering

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Android)

## Contributing

1. Follow the [CLAUDE.md](../../CLAUDE.md) coding guidelines
2. Write tests for new features
3. Update documentation when adding features
4. Run type checking and linting before committing
5. Use conventional commit messages

## Troubleshooting

### Port 3000 already in use

```bash
# Find and kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

### Type errors after installing dependencies

```bash
# Clean install
rm -rf node_modules pnpm-lock.yaml
pnpm install
```

### Playwright tests failing

```bash
# Install/update Playwright browsers
pnpm exec playwright install

# Clear test artifacts
rm -rf test-results playwright-report
```

## License

Proprietary - All rights reserved
