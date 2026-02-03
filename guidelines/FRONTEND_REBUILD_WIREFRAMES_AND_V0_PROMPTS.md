# Frontend Rebuild Wireframes + v0.dev Prompt Pack

This document captures the complete set of:
- Global wireframes (shell + overlays)
- Page wireframes (all current routes)
- Professional v0.dev prompts (shell + every page)

Source basis:
- `guidelines/UX-UI-Design-To-Implement-Process.md`
- `guidelines/COMPREHENSIVE_UX_UI_GUIDELINES.md`
- `guidelines/COMPREHENSIVE_STYLE_GUIDELINES.md`

Assumptions confirmed:
- Alerts are **drawer + toast** (no Alerts route).
- Help is **contextual help + drawer** (no `/help` route).

---

## Global Wireframes (Apply Everywhere)

### G0 — Responsive Grid + Breakpoints (Hard Requirements)
- Breakpoints: `sm=640`, `md=768`, `lg=1024`, `xl=1280` (mobile-first).
- Grid mental model:
  - **Desktop (≥1280)**: 12-col, sidebar expanded, multi-panel layouts.
  - **Tablet (768–1023)**: 8-col, sidebar collapses, secondary panels stack.
  - **Mobile (≤767)**: 4-col, single-column, full-width inputs/buttons, hamburger menu.
- Spacing hierarchy:
  - Macro: 64px+ between major sections
  - Section: 32–48px between blocks
  - Element: 16–24px between related groups
  - Micro: 4–12px within components
- Touch: minimum 44px targets on touch devices.
- Motion:
  - Use only tokenized durations (`--anim-fast/medium/slow` or equivalent).
  - Support `prefers-reduced-motion` (disable transforms/transitions).

### G1 — Authenticated App Shell Wireframe

**Layout regions**
- Left: **Sidebar** (collapsible)
  - Items (6): Dashboard, Trades, Portfolio, History, Analytics, Settings
  - Collapsed mode: icons + tooltips; expanded mode: icon + label
  - Mobile: sidebar becomes Sheet (hamburger button)
- Top: **Topbar**
  - Left cluster: hamburger (mobile), app name/logo (click to Dashboard)
  - Center cluster: **Symbol Command/Combobox**, **Timeframe segmented control**
  - Right cluster: **Connection status pill**, **Alerts bell (badge count)**, **Help (?)**, **User menu**, **Command palette button**
- Main: **Content canvas**
  - Breadcrumb/title row optional per page
  - Page content uses consistent padding + max-width rules
- Overlays (global):
  - **Command Palette (Ctrl+K)** (no route)
  - **Alerts Center Drawer** (no route)
  - **Help Drawer** (no route)
  - **Toasts stack** (no route)

**Global states**
- Offline/reconnecting banner at top of content area (or topbar strip)
- “Last updated” timestamp surfaces on data-heavy pages
- Skeleton pattern for loading blocks (fixed heights to prevent CLS)

### G2 — Command Palette Wireframe (Nielsen #7)
- Trigger: `Ctrl+K` + topbar button
- Modal contents:
  - Search input
  - Groups:
    - Navigate: the 6 routes
    - Actions: toggle overlays; go to symbol; set timeframe; open alerts/help
    - Trading actions: disabled when offline; destructive actions require confirm
- Keyboard:
  - Up/down selects, Enter executes, Esc closes
- Accessibility:
  - Focus trap, proper aria labels, visible focus rings
- Reduced motion:
  - No transform animation when `prefers-reduced-motion`

### G3 — Alerts System Wireframe (Drawer + Toast)

**Toast stack (low/medium priority)**
- Position:
  - Desktop: top-right
  - Mobile: bottom
- Stack: vertical, **8px gap**
- Card spec:
  - Icon 20px + title + message
  - Padding **12px vertical / 16px horizontal**
  - Radius 4px
  - Left border color by priority/status; tinted background
- Timing:
  - Low/Medium auto-dismiss at **5s**
  - High/Critical persist until dismissed
- Error message structure for errors:
  - “What happened” + “Why” + “How to fix”

**Alerts Center Drawer**
- Trigger: bell icon
- Header: “Alerts” + unread count + “Mark all read”
- Tabs: All / Unread / High
- List items follow same card spec; actions: mark read, delete, filter/search
- Drawer supports keyboard navigation and Escape to close

### G4 — Contextual Help (Nielsen #10, no route)
- Trigger: “?” icon
- Right-side drawer:
  - Keyboard shortcuts cheat sheet (Ctrl+K, etc.)
  - Glossary (Guards, Exposure, Venue, ReduceOnly, TTL, etc.)
  - Context block: changes by current route
- Inline tooltips:
  - Info icon next to complex fields (risk settings, guards, leverage, etc.)
  - Tooltip uses short, scannable help; links to open Help Drawer to full details

---

## Page Wireframes (All Pages)

### P0 — `/login`
**Goal:** fast sign-in, strong error recovery, keyboard-first.
- Centered auth card
  - Title + short subtitle
  - Email input (label + helper + inline error)
  - Password input (label + helper + inline error)
  - Remember me checkbox
  - Primary CTA: Sign in (loading state)
- Banners inside card:
  - Session ended (from cross-tab) banner
  - Login error banner using “what/why/how”
- Keyboard:
  - Enter submits
  - Visible focus states

### P1 — `/` Dashboard (Monitoring)
**Goal:** safety + system status first, then performance, then account.
- Section A (Safety row):
  - Guard Status panel (SAFE/BLOCK pills + last updated)
  - Exposure panel (net exposure, long/short, by venue)
  - Emergency controls (danger buttons + confirm modal)
- Section B (Performance):
  - KPI cards (PnL, win rate, drawdown, active signals)
  - Equity curve panel
- Section C (System):
  - Pipeline health list (ingest/features/smc/decision/router)
  - Engine status + auto-trading toggle
- Section D (Account):
  - Positions table
  - Balances table
- Global:
  - Alerts preview snippet + “View all” (opens Alerts drawer)
  - Offline banner + stale timestamps

### P2 — `/trades` Trading Terminal
**Goal:** correct execution with low cognitive load; performance-safe charting.
- Top controls row:
  - Symbol combobox
  - Venue toggle (SPOT / USD-M)
  - Timeframe segmented
  - Overlay toggles (EMA/RSI/MACD, Zones, Events)
  - Connection status
- Main: resizable layout
  - Panel 1 (Chart):
    - Chart canvas placeholder (imperative island concept)
    - Overlay legend
  - Panel 2 (Order Ticket):
    - Tabs: Market / Limit / Stop
    - Side toggle (Buy/Sell)
    - Quantity with Max
    - Conditional price / stop price
    - Bracket preview (entry/SL/TP ladder)
    - Submit (confirm dialog)
    - Inline validation (error prevention)
  - Panel 3 (Bottom tabs):
    - Open Orders (cancel with confirm)
    - Positions
    - Fills (if available)
- States:
  - Offline disables submit and shows “how to fix” guidance
  - Error surfaces near the action, not only global toast
- Keyboard:
  - Ctrl+K palette; tab order; Esc closes modals; Enter submits after confirm

### P3 — `/portfolio`
**Goal:** exposure + balances clarity; fast scanning.
- Summary row:
  - Total value, total PnL, open positions count
- Allocation/exposure row:
  - Allocation by asset (placeholder)
  - Exposure by venue + risk warnings
- Tables:
  - Positions table (sort, filter non-zero, highlight PnL)
  - Balances table (USD value, unknown state)
- States:
  - If pricing missing: explicit “USD value unavailable” (no silent 0)

### P4 — `/history`
**Goal:** audit trail + review with low friction.
- Filter row:
  - Date range chips
  - Symbol search
  - Side/status filter
  - Export action (secondary)
- Table:
  - Filled orders list
  - Row expands to details drawer (IDs, timestamps, venue, fees if available)
- States:
  - Empty state suggests widening filters

### P5 — `/analytics`
**Goal:** performance insight, not just numbers.
- Controls:
  - Timeframe segmented + compare toggle
- KPI grid:
  - Total return, win rate, profit factor, sharpe, max DD
- Charts:
  - Equity curve, drawdown curve, distribution (placeholders)
- Table:
  - Performance by symbol (sortable)
- States:
  - Progressive skeleton loading to keep layout stable

### P6 — `/settings`
**Goal:** prevent mistakes; clear risk and integration status.
- Tabs:
  - General / Trading / Notifications / API Keys
- General:
  - Theme, timezone, language
- Trading:
  - Default venue/leverage
  - Confirm orders
  - Max position size
  - Default SL/TP
  - Inline warnings/tooltips for risky fields
- Notifications:
  - toggles (email, executions, system alerts)
- API Keys:
  - Spot/Futures connection status cards
  - Testnet toggle
  - “Last verified” timestamp
- Actions:
  - Save (success toast), Reset to defaults (confirm modal)

---

## Professional v0.dev Prompt Pack

### Base Prompt Preamble (paste at top of every v0 prompt)
```text
Build target:
- Next.js App Router + TypeScript.
- Use shadcn/ui components + Tailwind (no custom primitive re-implementation).
- Dark, modern trading aesthetic; high contrast; minimal clutter; crisp typography.

Hard requirements from our internal guidelines:
- Responsive breakpoints: 640 / 768 / 1024 / 1280 (mobile-first).
- Grid mental model: 12-col desktop, 8-col tablet, 4-col mobile.
- 8px spacing system + spacing hierarchy (macro/section/element/micro).
- Touch targets >= 44px on touch devices.
- All interactive components support states: default/hover/active/focus/disabled/loading/error.
- Include explicit Empty/Loading/Error/Offline UI for data-driven areas.
- Alerts: toast stack (8px gap) with 12px/16px padding, 4px radius, icon 20px, colored left border; auto-dismiss low/medium at 5s; high persists.
- Error copy follows: What happened + Why + How to fix.
- Motion uses tokenized durations only; support prefers-reduced-motion (disable transitions/transforms).

Implementation constraints:
- No real API calls. Use placeholder objects/arrays.
- Avoid inline styles; use Tailwind classes.
- Use semantic color + spacing tokens (no raw hex, no arbitrary values).
```

### Shell Prompt — Authenticated App Shell (includes overlays)
```text
Create the authenticated App Shell for a trading platform.

Layout:
- Left Sidebar (collapsible):
  - Nav items (6): Dashboard (/), Trades (/trades), Portfolio (/portfolio), History (/history), Analytics (/analytics), Settings (/settings).
  - Expanded: icon + label. Collapsed: icons only with tooltips.
  - Mobile: sidebar becomes a Sheet opened by a hamburger button.
- Topbar:
  - Left: hamburger (mobile), app logo/title.
  - Center: Symbol combobox (Command/Popover) with recent symbols + search; Timeframe segmented control (1m/5m/15m/1h/4h/1d).
  - Right: Connection status pill (Connected/Reconnecting/Offline), Alerts bell button with unread badge, Help (?) button, Command Palette button, User dropdown.
- Main content:
  - Render children content area with consistent padding and max width rules.
  - Include an optional page title slot.

Global overlays (must be included in the shell component):
1) Command Palette (Ctrl+K):
  - Use shadcn Command in a Dialog.
  - Groups: Navigate (routes), Actions (toggle overlays, open alerts/help), Data (go to symbol, set timeframe).
  - Keyboard nav + ESC close + focus trap.
2) Alerts:
  - Toast stack component (desktop top-right, mobile bottom), vertical stack with 8px gap; auto-dismiss low/medium at 5s; high persists.
  - Alerts Center drawer (Sheet) opened from bell icon, tabs All/Unread/High, list items with actions (mark read/delete).
3) Help:
  - Help drawer (Sheet) opened from ? icon containing shortcuts + glossary + route-specific help section.
  - Reusable Tooltip pattern for info icons.

States:
- Show an Offline/Reconnecting banner strip in the content area when not connected.
- Provide placeholder app state for: connection state, unread alerts count, current user.

Accessibility:
- Proper aria-labels on icon buttons.
- Visible focus rings.
- Skip link support.
- Reduced motion support.

Output:
- Produce the shell layout component + minimal child placeholder.
- Use clean component decomposition (Shell, Sidebar, Topbar, CommandPalette, AlertsDrawer, ToastStack, HelpDrawer).
- No real routing logic; use placeholder handlers.
```

### Login — `/login`
```text
Create a modern Login page (standalone, not inside the authenticated shell).

Content:
- Centered card on dark background with subtle gradient.
- Title: “Trading Platform” + subtitle.
- Email + password fields with labels, helper text, inline validation error areas.
- Remember me checkbox.
- Primary button: Sign in (loading state).
- Banner areas inside card:
  - Session notification banner (info).
  - Login error banner that follows: What happened + Why + How to fix.
- Add a secondary link-style action: “Need help?” (opens a small modal explaining credential format).

States:
- Loading state disables inputs and shows spinner in button.
- Error state shows banner + field-level error.

Accessibility:
- Correct label/for associations.
- Keyboard: Enter submits; focus order correct; visible focus.
- Touch targets >= 44px.

No API calls, placeholder handlers only.
```

### Dashboard — `/`
```text
Create the Dashboard / Monitoring page content for a trading platform (content rendered inside the App Shell).

Layout (desktop):
- Section A (Safety grid, 3 panels):
  1) Guard Status panel: list of guard pills SAFE/BLOCK with last updated timestamps; info tooltip icons.
  2) Exposure panel: net exposure, long/short breakdown, by venue; show warning styling when thresholds exceeded.
  3) Emergency controls panel: danger actions (Emergency Close / Stop Engine) with confirmation dialog.
- Section B (Performance):
  - KPI card grid (PnL, win rate, drawdown, active signals).
  - Equity curve panel placeholder.
- Section C (System status):
  - Pipeline health list: ingest/features/smc/decision/router rows with status + latency placeholders.
  - Engine status card + auto-trading toggle.
- Section D (Account):
  - Positions table.
  - Balances table.

Required states:
- Loading: skeletons for each panel with fixed heights.
- Empty: meaningful empty content (e.g., “No positions yet”).
- Error: panel-level error using what/why/how to fix.
- Offline: show an offline banner and “data may be stale” note.

Responsive:
- Tablet: stack into 1–2 columns; sidebar collapses.
- Mobile: single column; tables become horizontally scrollable or card-stacked.

Use shadcn: Card, Badge, Alert, Skeleton, Table, Tooltip, Dialog, Switch.
No real data; use placeholder objects.
```

### Trades — `/trades`
```text
Create the Trades (Trading Terminal) page content (rendered inside the App Shell).

Top controls row:
- Symbol combobox (search + recent).
- Venue toggle (SPOT / USD-M).
- Timeframe segmented control.
- Overlay toggles (EMA/RSI/MACD, Zones, Events) as a compact group.
- Connection status is shown in the shell already, but include a local “Last update” timestamp.

Main layout:
- Use shadcn Resizable panels (desktop):
  - Left: Chart panel (large) with chart placeholder canvas, overlay legend, and small indicator chips.
  - Right: Order Ticket card:
    - Tabs: Market / Limit / Stop
    - Side toggle (Buy green / Sell red)
    - Quantity input with Max button
    - Conditional fields: price (Limit), stop price (Stop)
    - Bracket preview list (Entry/SL/TP ladder)
    - Primary CTA: Place Order -> confirm dialog before final submit
    - Inline validation + error prevention messaging
- Bottom panel:
  - Tabs: Open Orders / Positions / Fills
  - Tables with actions (Cancel for open orders, with confirm dialog)

Required states:
- Loading: skeleton in tables and order submit button spinner.
- Empty: no orders/positions messaging with next action suggestions.
- Error: show error banners near action + toast for summary.
- Offline: disable submit and cancel actions; show “How to fix” guidance.

Keyboard & a11y:
- Full keyboard navigation, visible focus.
- Confirm dialogs trap focus; ESC closes.
- Tooltips on advanced fields (venue, stop price, reduce-only).

No real API calls; placeholder data arrays for orders/positions/fills.
```

### Portfolio — `/portfolio`
```text
Create the Portfolio page content (inside the App Shell).

Layout:
- Summary cards row:
  - Total Portfolio Value
  - Total PnL (positive/negative styling)
  - Open Positions count
- Secondary row:
  - Allocation by asset (placeholder chart or list)
  - Exposure by venue + risk badge
- Tables:
  - Positions table (sortable headers, quick filter chips)
  - Balances table (free/locked/total/usd value; “USD unavailable” state)

Required states:
- Loading: skeletons with fixed heights.
- Empty: friendly empty states for positions and balances.
- Error: what/why/how banners.
- Offline: stale indicator.

Responsive:
- Tablet: 2-column layout where possible.
- Mobile: single column; tables scroll horizontally or become stacked cards.

Use shadcn: Card, Table, Badge, Skeleton, Alert, Tabs/Segmented controls.
```

### History — `/history`
```text
Create the History page content (inside the App Shell).

Top filter bar:
- Date range chips (24H, 7D, 30D, All).
- Symbol search (combobox).
- Side filter (Buy/Sell/All).
- Status filter (Filled/Cancelled/etc).
- Export button (secondary) with dropdown (CSV/JSON).

Main:
- Trades table:
  - Date/time, symbol, side, type, avg price, qty, total, status.
  - Row click opens a details drawer with full info (ids, venue, timestamps, fee placeholder).

Required states:
- Loading: skeleton table.
- Empty: “No trades in this period” + suggestion to widen filters.
- Error: what/why/how.
- Offline: stale indicator.

Responsive:
- Mobile: filters wrap into a Sheet; table becomes scrollable.

Use shadcn: Table, DropdownMenu, Sheet, Badge, Skeleton, Alert.
```

### Analytics — `/analytics`
```text
Create the Analytics page content (inside the App Shell).

Controls:
- Timeframe segmented control (24h/7d/30d/90d/1y/all).
- Compare toggle (previous period).

KPI grid:
- Total return, win rate, profit factor, sharpe ratio, max drawdown.

Charts section:
- Equity curve placeholder
- Drawdown curve placeholder
- Win/Loss distribution placeholder

Table:
- Performance by symbol (sortable)

Required states:
- Loading: skeletons for KPI + charts.
- Empty: “Not enough data” messaging.
- Error: what/why/how to fix.
- Offline: stale indicator.

Responsive:
- Tablet stacks charts; mobile shows one chart at a time via tabs.

Use shadcn: Card, Tabs, Table, Skeleton, Alert, Switch.
```

### Settings — `/settings`
```text
Create the Settings page content (inside the App Shell).

Tabs:
- General / Trading / Notifications / API Keys.

General tab:
- Theme selector (dark/light)
- Timezone select
- Language select

Trading tab:
- Default venue
- Default leverage
- Confirm orders toggle
- Max position size input
- Default SL/TP inputs
- Inline warnings + tooltips for risky settings
- “Reset to defaults” (confirm dialog)

Notifications tab:
- Email alerts, trade executions, price alerts, system alerts toggles

API Keys tab:
- Status cards for Spot and Futures connections
- Testnet toggle
- “Last verified” timestamp and “Verify now” button (placeholder)

Actions:
- Save button with success toast
- Errors follow what/why/how

Required states:
- Loading skeleton (optional).
- Error banner.
- Offline warning for “Verify now”.

Responsive:
- Mobile tabs become a select/segmented control; forms are full-width.

Use shadcn: Tabs, Select, Switch, Input, Card, Alert, Tooltip, Dialog, Toast.
```

