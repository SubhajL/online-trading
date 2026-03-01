# Trading App Design System Specification

> **Version:** 1.0.0  
> **Last Updated:** 2025-02-03  
> **For Use With:** Claude Code, Cursor, GitHub Copilot, Google Stitch, v0.dev

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Tokens](#2-design-tokens)
3. [Typography](#3-typography)
4. [Spacing & Layout](#4-spacing--layout)
5. [Components](#5-components)
6. [Page Templates](#6-page-templates)
7. [AI Prompt Templates](#7-ai-prompt-templates)
8. [Consistency Checklist](#8-consistency-checklist)

---

## 1. Overview

### 1.1 Application Structure

| Page | Purpose | Layout Type |
|------|---------|-------------|
| **Dashboard** | Real-time monitoring, KPIs, system status | Bento grid, high density |
| **Trades** | Active/pending orders, execute trades | Table + action panels |
| **Portfolio** | Holdings, allocation, performance | Cards + charts |
| **History** | Past transactions, export data | Filterable data table |
| **Analytics** | Deep metrics, reports, insights | Charts + KPIs |
| **Settings** | User preferences, API config, alerts | Sidebar + forms |

### 1.2 Tech Stack

```yaml
Framework: React / Next.js
Styling: Tailwind CSS
Icons: Material Symbols Outlined
Fonts: Inter (Google Fonts)
Charts: Recharts / Chart.js
```

### 1.3 Design Philosophy

- **Clean & Professional:** Fintech-grade aesthetics
- **Data-Dense:** Efficient information display
- **Consistent:** Unified visual language across all pages
- **Accessible:** WCAG 2.1 AA compliant
- **Dark Mode Ready:** Full light/dark theme support

---

## 2. Design Tokens

### 2.1 Colors

```css
/* =========================================
   BRAND COLORS
   ========================================= */
--color-primary: #6464f2;
--color-primary-hover: #5353d9;
--color-primary-dark: #4f4fc1;
--color-primary-light: #8585f5;
--color-primary-bg: rgba(100, 100, 242, 0.1);

/* =========================================
   SEMANTIC COLORS
   ========================================= */
--color-success: #22c55e;
--color-success-light: #dcfce7;
--color-success-dark: #15803d;

--color-danger: #ef4444;
--color-danger-light: #fee2e2;
--color-danger-dark: #b91c1c;

--color-warning: #f59e0b;
--color-warning-light: #fef3c7;
--color-warning-dark: #b45309;

--color-info: #3b82f6;
--color-info-light: #dbeafe;
--color-info-dark: #1d4ed8;

/* =========================================
   SURFACE COLORS (Light Mode)
   ========================================= */
--bg-page: #FAFBFC;
--bg-surface: #FFFFFF;
--bg-surface-secondary: #F8FAFC;
--bg-surface-hover: #F1F5F9;

/* =========================================
   SURFACE COLORS (Dark Mode)
   ========================================= */
--bg-page-dark: #101022;
--bg-surface-dark: #1a1a2e;
--bg-surface-secondary-dark: #232340;
--bg-surface-hover-dark: #2a2a4a;

/* =========================================
   TEXT COLORS (Light Mode)
   ========================================= */
--text-primary: #0f172a;
--text-secondary: #475569;
--text-muted: #64748b;
--text-disabled: #94a3b8;
--text-placeholder: #cbd5e1;

/* =========================================
   TEXT COLORS (Dark Mode)
   ========================================= */
--text-primary-dark: #ffffff;
--text-secondary-dark: #e2e8f0;
--text-muted-dark: #94a3b8;
--text-disabled-dark: #64748b;

/* =========================================
   BORDER COLORS
   ========================================= */
--border-default: #e2e8f0;
--border-light: #f1f5f9;
--border-dark-mode: #334155;
--border-focus: rgba(100, 100, 242, 0.5);

/* =========================================
   TRADING-SPECIFIC COLORS
   ========================================= */
--color-long: #22c55e;      /* Green for LONG/BUY */
--color-long-bg: #dcfce7;
--color-short: #ef4444;     /* Red for SHORT/SELL */
--color-short-bg: #fee2e2;
--color-profit: #22c55e;    /* Green for profit */
--color-loss: #ef4444;      /* Red for loss */
--color-neutral: #64748b;   /* Gray for no change */
```

### 2.2 Tailwind Config

```javascript
// tailwind.config.js
module.exports = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "primary": "#6464f2",
        "primary-dark": "#4f4fc1",
        "danger": "#ef4444",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "background-light": "#FAFBFC",
        "background-dark": "#101022",
        "surface-light": "#FFFFFF",
        "surface-dark": "#1a1a2e",
      },
      fontFamily: {
        "display": ["Inter", "sans-serif"],
        "body": ["Inter", "sans-serif"],
        "mono": ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        "DEFAULT": "0.5rem",
        "lg": "0.75rem",
        "xl": "1rem",
        "2xl": "1.5rem",
      },
      boxShadow: {
        "soft": "0 4px 20px -2px rgba(0, 0, 0, 0.05)",
        "glow-success": "0 0 8px rgba(34, 197, 94, 0.5)",
        "glow-danger": "0 0 8px rgba(239, 68, 68, 0.5)",
        "glow-warning": "0 0 8px rgba(245, 158, 11, 0.5)",
      },
    },
  },
}
```

### 2.3 Shadow System

| Name | Value | Usage |
|------|-------|-------|
| `shadow-soft` | `0 4px 20px -2px rgba(0,0,0,0.05)` | Cards, panels |
| `shadow-sm` | `0 1px 2px 0 rgba(0,0,0,0.05)` | Buttons, inputs |
| `shadow-md` | `0 4px 6px -1px rgba(0,0,0,0.1)` | Dropdowns, hover |
| `shadow-lg` | `0 10px 15px -3px rgba(0,0,0,0.1)` | Modals, popovers |

### 2.4 Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `rounded-md` | 8px | Buttons, inputs, badges |
| `rounded-lg` | 12px | Small cards, table headers |
| `rounded-xl` | 16px | Medium cards, modals |
| `rounded-2xl` | 24px | Main cards, panels |
| `rounded-full` | 9999px | Pills, avatars, dots |

---

## 3. Typography

### 3.1 Font Stack

```css
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
```

### 3.2 Type Scale

| Class | Size | Weight | Usage |
|-------|------|--------|-------|
| `text-4xl` | 36px | Bold | Hero numbers |
| `text-3xl` | 30px | Bold | Large stat values |
| `text-2xl` | 24px | Bold | Page titles |
| `text-xl` | 20px | Bold | Card titles |
| `text-lg` | 18px | Semibold | Section headers |
| `text-base` | 16px | Normal | Body text |
| `text-sm` | 14px | Normal/Medium | Secondary text, table cells |
| `text-xs` | 12px | Medium/Semibold | Labels, badges, captions |
| `text-[10px]` | 10px | Medium | Micro labels |

### 3.3 Typography Classes

```html
<!-- Page Title -->
<h1 class="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
  Page Title
</h1>

<!-- Page Subtitle -->
<p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
  Page description text
</p>

<!-- Card Title -->
<h3 class="text-lg font-bold text-slate-900 dark:text-white">
  Card Title
</h3>

<!-- Section Label (Uppercase) -->
<span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">
  LABEL
</span>

<!-- Stat Value -->
<span class="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">
  $142,350
</span>

<!-- Table Header -->
<th class="text-xs font-semibold text-slate-400 uppercase tracking-wider">
  Column Name
</th>

<!-- Monospace (prices, numbers) -->
<span class="font-mono tabular-nums">
  64,350.00
</span>
```

---

## 4. Spacing & Layout

### 4.1 Spacing Scale (4px Base)

| Token | Value | Tailwind |
|-------|-------|----------|
| `--space-1` | 4px | `p-1`, `m-1`, `gap-1` |
| `--space-2` | 8px | `p-2`, `m-2`, `gap-2` |
| `--space-3` | 12px | `p-3`, `m-3`, `gap-3` |
| `--space-4` | 16px | `p-4`, `m-4`, `gap-4` |
| `--space-5` | 20px | `p-5`, `m-5`, `gap-5` |
| `--space-6` | 24px | `p-6`, `m-6`, `gap-6` |
| `--space-8` | 32px | `p-8`, `m-8`, `gap-8` |
| `--space-10` | 40px | `p-10`, `m-10`, `gap-10` |
| `--space-12` | 48px | `p-12`, `m-12`, `gap-12` |

### 4.2 Layout Constants

```css
/* Page Layout */
--page-max-width: 1400px;
--page-padding-x: 24px;   /* px-6 */
--page-padding-y: 32px;   /* py-8 */

/* Card Layout */
--card-padding: 24px;     /* p-6 */
--card-gap: 24px;         /* gap-6 */

/* Component Spacing */
--input-height: 40px;     /* h-10 */
--button-padding-x: 16px; /* px-4 */
--button-padding-y: 10px; /* py-2.5 */
```

### 4.3 Grid System

```html
<!-- Page Container -->
<main class="flex-1 w-full max-w-[1400px] mx-auto px-6 py-8">
  
  <!-- Bento Grid (Dashboard, Analytics) -->
  <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
    <div class="md:col-span-3">...</div>
    <div class="md:col-span-6">...</div>
    <div class="md:col-span-3">...</div>
  </div>
  
  <!-- Two Column (Trades, Portfolio) -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
    <div class="lg:col-span-8">...</div>
    <div class="lg:col-span-4">...</div>
  </div>
  
  <!-- Sidebar Layout (Settings) -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
    <div class="lg:col-span-3"><!-- Sidebar --></div>
    <div class="lg:col-span-9"><!-- Content --></div>
  </div>
  
</main>
```

### 4.4 Breakpoints

| Name | Min Width | Usage |
|------|-----------|-------|
| `sm` | 640px | Mobile landscape |
| `md` | 768px | Tablet |
| `lg` | 1024px | Desktop |
| `xl` | 1280px | Large desktop |

---

## 5. Components

### 5.1 Page Shell

```html
<!-- HEADER (Same on ALL pages) -->
<header class="sticky top-0 z-50 bg-white dark:bg-surface-dark border-b border-slate-100 dark:border-slate-800/50">
  <div class="max-w-[1400px] mx-auto px-6">
    <div class="flex items-center justify-between h-[72px]">
      
      <!-- Left: Logo + Nav -->
      <div class="flex items-center gap-8">
        <!-- Logo -->
        <div class="flex items-center gap-3">
          <div class="size-8 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
            <span class="material-symbols-outlined filled-icon">candlestick_chart</span>
          </div>
          <h2 class="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Online Trader</h2>
        </div>
        
        <!-- Search (hidden on mobile) -->
        <div class="hidden md:flex items-center bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl h-10 w-64">
          <span class="material-symbols-outlined text-slate-400 pl-3 text-[20px]">search</span>
          <input class="bg-transparent border-none focus:ring-0 text-sm pl-2 w-full" placeholder="Search markets...">
        </div>
      </div>
      
      <!-- Center: Navigation -->
      <nav class="hidden lg:flex items-center gap-6">
        <a href="/dashboard" class="nav-link">Dashboard</a>
        <a href="/trades" class="nav-link">Trades</a>
        <a href="/portfolio" class="nav-link">Portfolio</a>
        <a href="/history" class="nav-link">History</a>
        <a href="/analytics" class="nav-link">Analytics</a>
        <a href="/settings" class="nav-link">Settings</a>
      </nav>
      
      <!-- Right: Actions -->
      <div class="flex items-center gap-3 border-l border-slate-100 dark:border-slate-800 pl-6">
        <!-- Notifications -->
        <button class="relative size-10 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-300">
          <span class="material-symbols-outlined">notifications</span>
          <span class="absolute top-2.5 right-2.5 size-2 bg-red-500 rounded-full"></span>
        </button>
        
        <!-- User Menu -->
        <button class="flex items-center gap-2 pl-1 pr-3 py-1 rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
          <div class="size-8 rounded-full bg-primary/20"></div>
          <span class="text-xs font-semibold text-slate-700 dark:text-slate-200">Alex T.</span>
        </button>
      </div>
      
    </div>
  </div>
</header>

<!-- Navigation Link Styles -->
<style>
  .nav-link {
    @apply text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-primary transition-colors;
  }
  .nav-link.active {
    @apply text-primary font-semibold;
  }
</style>
```

### 5.2 Page Header

```html
<!-- PAGE HEADER (Same structure on ALL pages) -->
<div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
  <div>
    <h1 class="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
      [Page Title]
    </h1>
    <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
      [Page description]
    </p>
  </div>
  <div class="flex items-center gap-3">
    <!-- Page-specific actions -->
  </div>
</div>
```

### 5.3 Cards

```html
<!-- Standard Card -->
<div class="bg-white dark:bg-surface-dark rounded-2xl shadow-soft p-6">
  <!-- Card content -->
</div>

<!-- Card with Header -->
<div class="bg-white dark:bg-surface-dark rounded-2xl shadow-soft p-6">
  <div class="flex items-center gap-3 mb-4">
    <div class="p-2 bg-primary/10 rounded-lg text-primary">
      <span class="material-symbols-outlined">icon_name</span>
    </div>
    <h3 class="text-lg font-bold text-slate-900 dark:text-white">Card Title</h3>
  </div>
  <!-- Card content -->
</div>

<!-- Card with Left Border Accent -->
<div class="bg-white dark:bg-surface-dark rounded-2xl shadow-soft border-l-4 border-primary p-6">
  <!-- Card content -->
</div>

<!-- Card with Top Border Accent (Danger) -->
<div class="bg-white dark:bg-surface-dark rounded-2xl shadow-soft border-t-4 border-danger p-6">
  <!-- Card content -->
</div>
```

### 5.4 Buttons

```html
<!-- Primary Button -->
<button class="bg-primary hover:bg-primary-dark text-white font-semibold py-2.5 px-4 rounded-xl shadow-sm transition-all">
  Primary Action
</button>

<!-- Secondary Button -->
<button class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium py-2.5 px-4 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700 transition-all">
  Secondary Action
</button>

<!-- Danger Button -->
<button class="bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white font-bold py-3 px-4 rounded-xl shadow-md transition-all">
  Danger Action
</button>

<!-- Ghost Button -->
<button class="text-primary hover:text-primary-dark font-medium text-sm transition-colors">
  Text Link
</button>

<!-- Icon Button -->
<button class="size-10 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-300 transition-colors">
  <span class="material-symbols-outlined">icon</span>
</button>

<!-- Button with Icon -->
<button class="flex items-center gap-2 bg-primary hover:bg-primary-dark text-white font-semibold py-2.5 px-4 rounded-xl transition-all">
  <span class="material-symbols-outlined text-[18px]">add</span>
  Add New
</button>
```

### 5.5 Form Inputs

```html
<!-- Text Input -->
<input 
  type="text"
  class="w-full h-10 px-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:border-primary/50 focus:ring-0 transition-colors"
  placeholder="Placeholder text"
/>

<!-- Input with Label -->
<label class="block">
  <span class="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1.5 block">Label</span>
  <input type="text" class="w-full h-10 px-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:border-primary/50 focus:ring-0 transition-colors" />
</label>

<!-- Select -->
<select class="w-full h-10 px-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-700 dark:text-slate-200 focus:border-primary/50 focus:ring-0 transition-colors">
  <option>Option 1</option>
  <option>Option 2</option>
</select>

<!-- Search Input with Icon -->
<div class="flex items-center bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl h-10 focus-within:border-primary/50 transition-colors">
  <span class="material-symbols-outlined text-slate-400 pl-3 text-[20px]">search</span>
  <input type="text" class="w-full bg-transparent border-none focus:ring-0 text-sm pl-2 pr-4" placeholder="Search..." />
</div>

<!-- Toggle Switch -->
<label class="relative inline-flex items-center cursor-pointer">
  <input type="checkbox" class="sr-only peer" checked />
  <div class="w-14 h-8 bg-slate-200 rounded-full peer dark:bg-slate-700 peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-7 after:w-7 after:transition-all"></div>
</label>
```

### 5.6 Tables

```html
<!-- Data Table -->
<div class="overflow-x-auto">
  <table class="w-full text-left text-sm whitespace-nowrap">
    <thead class="bg-slate-50 dark:bg-slate-800/50">
      <tr>
        <th class="px-4 py-3 font-semibold text-xs text-slate-500 uppercase tracking-wider rounded-l-lg">Column 1</th>
        <th class="px-4 py-3 font-semibold text-xs text-slate-500 uppercase tracking-wider">Column 2</th>
        <th class="px-4 py-3 font-semibold text-xs text-slate-500 uppercase tracking-wider text-right rounded-r-lg">Column 3</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
        <td class="px-4 py-4 font-medium text-slate-800 dark:text-white">Data</td>
        <td class="px-4 py-4 text-slate-600 dark:text-slate-300">Data</td>
        <td class="px-4 py-4 text-right text-slate-500">Data</td>
      </tr>
    </tbody>
  </table>
</div>
```

### 5.7 Badges & Tags

```html
<!-- Status Badge (Pill) -->
<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200">
  ACTIVE
</span>

<!-- Type Badge (Rectangular) -->
<span class="px-3 py-1 rounded-lg text-xs font-bold bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 border border-blue-100 dark:border-blue-800">
  SPOT
</span>

<!-- LONG Badge -->
<span class="px-2.5 py-1 rounded text-xs font-bold bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
  LONG
</span>

<!-- SHORT Badge -->
<span class="px-2.5 py-1 rounded text-xs font-bold bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
  SHORT
</span>

<!-- Status Variants -->
<span class="badge-success">Success</span>
<span class="badge-warning">Warning</span>
<span class="badge-danger">Error</span>
<span class="badge-info">Info</span>

<style>
  .badge-success { @apply px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200; }
  .badge-warning { @apply px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-700 border border-amber-200; }
  .badge-danger { @apply px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700 border border-red-200; }
  .badge-info { @apply px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-700 border border-blue-200; }
</style>
```

### 5.8 Status Indicators

```html
<!-- Status Dot -->
<span class="size-2 rounded-full bg-emerald-500"></span>  <!-- Running/Success -->
<span class="size-2 rounded-full bg-amber-500"></span>    <!-- Warning -->
<span class="size-2 rounded-full bg-red-500"></span>      <!-- Error -->
<span class="size-2 rounded-full bg-slate-400"></span>    <!-- Inactive -->

<!-- Glowing Status Dot -->
<span class="size-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></span>

<!-- Pulse Animation -->
<span class="size-2 rounded-full bg-emerald-500 animate-pulse"></span>

<!-- Status with Label -->
<span class="flex items-center gap-2 text-xs font-medium text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-100 dark:border-emerald-500/20">
  <span class="size-2 bg-emerald-500 rounded-full animate-pulse"></span>
  System Operational
</span>
```

### 5.9 KPI / Stat Tiles

```html
<!-- KPI Tile -->
<div class="p-4 rounded-xl bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/30 flex flex-col gap-1">
  <span class="text-xs text-slate-500 font-medium uppercase tracking-wider">Metric Name</span>
  <span class="text-xl font-bold text-slate-900 dark:text-white">64.2%</span>
  <span class="text-xs font-medium flex items-center gap-0.5 text-emerald-600">
    <span class="material-symbols-outlined text-[14px]">trending_up</span>
    +2.1%
  </span>
</div>

<!-- Color Variants -->
<!-- Blue: bg-blue-50, border-blue-100 -->
<!-- Purple: bg-purple-50, border-purple-100 -->
<!-- Orange: bg-orange-50, border-orange-100 -->
<!-- Emerald: bg-emerald-50, border-emerald-100 -->
```

### 5.10 Progress Bar

```html
<!-- Simple Progress Bar -->
<div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
  <div class="bg-gradient-to-r from-primary to-purple-500 h-3 rounded-full" style="width: 68%"></div>
</div>

<!-- Progress Bar with Label -->
<div>
  <div class="flex justify-between text-xs mb-2 font-medium">
    <span class="text-slate-600 dark:text-slate-300">Margin Utilization</span>
    <span class="text-primary font-bold">68%</span>
  </div>
  <div class="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
    <div class="bg-gradient-to-r from-primary to-purple-500 h-3 rounded-full" style="width: 68%"></div>
  </div>
</div>
```

---

## 6. Page Templates

### 6.1 Dashboard

```
Layout: 12-column bento grid
Gap: 24px (gap-6)

ROW 1:
├── Guard Status (col-span-3)
│   └── Left border accent, status list with dots
├── Total Exposure (col-span-6)
│   └── Large value, sub-metrics, progress bar
└── Emergency Controls (col-span-3)
    └── Top border (red), danger buttons

ROW 2:
├── Trading Performance (col-span-7 lg:col-span-8)
│   └── 4 KPI tiles, area chart
└── Right Column (col-span-5 lg:col-span-4)
    ├── Auto Trading toggle card
    └── Pipeline Health table

ROW 3:
├── Open Positions (col-span-8)
│   └── Table with symbol, side, prices, PNL
└── Assets (col-span-4)
    └── Account sections, crypto balances
```

### 6.2 Trades

```
Layout: Filters + Two columns

FILTERS BAR:
├── Symbol dropdown
├── Side filter
├── Type filter
├── Status filter
└── Search input

COLUMNS:
├── Left (col-span-8): Active Orders table
└── Right (col-span-4): Order Form card
    ├── Limit/Market/Stop tabs
    ├── Buy/Sell toggle
    ├── Price, Amount inputs
    └── Submit button

BOTTOM:
└── Recent Executions table
```

### 6.3 Portfolio

```
Layout: KPI row + Two columns + Chart

KPI ROW (4 tiles):
├── Total Value
├── 24h Change
├── Unrealized PNL
└── Available Balance

COLUMNS:
├── Left (col-span-8): Holdings table
└── Right (col-span-4)
    ├── Allocation donut chart
    └── Performance summary

BOTTOM:
└── Portfolio Value History chart
```

### 6.4 History

```
Layout: Filters + Full-width table

HEADER ACTIONS:
├── Date range picker
└── Export dropdown

FILTERS BAR:
├── Symbol multi-select
├── Type filter
├── Side filter
└── Status filter

TABLE:
├── Date/Time, Type, Symbol, Side
├── Amount, Price, Fee, Total
├── Status, Actions
└── Pagination
```

### 6.5 Analytics

```
Layout: Controls + KPIs + Charts

CONTROLS:
├── Date range picker
├── Compare toggle
└── Refresh button

KPI ROW (6 tiles):
├── Win Rate, Profit Factor, Sharpe
└── Max Drawdown, Total Trades, Net Profit

CHART ROW 1:
├── Equity Curve (col-span-8)
└── Drawdown Chart (col-span-4)

CHART ROW 2:
├── Trade by Hour (col-span-6)
└── Performance by Symbol (col-span-6)

BOTTOM:
└── Trade Journal table
```

### 6.6 Settings

```
Layout: Sidebar + Content

SIDEBAR (col-span-3):
├── Profile
├── Security
├── API Keys
├── Notifications
├── Trading Preferences
├── Appearance
└── Danger Zone (red)

CONTENT (col-span-9):
└── Form cards for selected section
```

---

## 7. AI Prompt Templates

### 7.1 Master Context Prompt

Use this prompt first when starting any page:

```
I'm building a cryptocurrency trading application. Apply this design system consistently:

COLORS:
- Primary: #6464f2 (indigo-purple)
- Success/Long/Profit: #22c55e (green)  
- Danger/Short/Loss: #ef4444 (red)
- Warning: #f59e0b (amber)
- Background: #FAFBFC
- Surface/Cards: #FFFFFF
- Text primary: #0f172a, secondary: #475569, muted: #64748b

TYPOGRAPHY:
- Font: Inter
- Page title: text-2xl font-bold tracking-tight
- Card title: text-lg font-bold
- Body: text-sm
- Labels: text-xs uppercase tracking-wider

SPACING & LAYOUT:
- Page max-width: 1400px, padding: px-6 py-8
- Card: rounded-2xl shadow-soft p-6
- Grid gap: gap-6 (24px)
- Button/Input radius: rounded-xl (16px)

COMPONENTS:
- Use Material Symbols Outlined icons
- Tables: rounded header corners, hover rows
- Badges: rounded-full for status, rounded-lg for types
- Status dots: size-2 rounded-full with color
```

### 7.2 Page-Specific Prompts

**Dashboard:**
```
Create the Dashboard page using the design system.

12-column bento grid layout with:
- Row 1: Guard Status (col-3), Exposure (col-6), Emergency (col-3)
- Row 2: Performance chart with KPIs (col-8), Auto Trading + Pipeline (col-4)
- Row 3: Open Positions table (col-8), Assets list (col-4)

Include system status badge with pulse animation in header.
```

**Trades:**
```
Create the Trades page using the design system.

Layout:
- Filters bar: Symbol, Side, Type, Status dropdowns + Search
- Left (col-8): Active Orders table
- Right (col-4): Order form with Limit/Market tabs, Buy/Sell toggle
- Bottom: Recent Executions table
```

**Portfolio:**
```
Create the Portfolio page using the design system.

Layout:
- 4 KPI tiles: Total Value, 24h Change, Unrealized PNL, Available Balance
- Left (col-8): Holdings table with allocation progress bars
- Right (col-4): Donut chart + Performance summary
- Bottom: Value history area chart
```

**History:**
```
Create the History page using the design system.

Layout:
- Header actions: Date range picker, Export button
- Filters: Symbol, Type, Side, Status
- Full-width transaction table with pagination
- Columns: Date, Type, Symbol, Side, Amount, Price, Fee, Total, Status
```

**Analytics:**
```
Create the Analytics page using the design system.

Layout:
- Date controls and compare toggle
- 6 KPI tiles: Win Rate, Profit Factor, Sharpe, Drawdown, Trades, Profit
- Equity curve chart (col-8) + Drawdown chart (col-4)
- Trade distribution charts (2 columns)
- Trade journal table at bottom
```

**Settings:**
```
Create the Settings page using the design system.

Layout:
- Left sidebar (col-3): Profile, Security, API Keys, Notifications, Preferences, Appearance, Danger Zone
- Right content (col-9): Form cards for selected section
- Active nav: primary color background
- Danger Zone: red border and text
```

---

## 8. Consistency Checklist

Before finalizing any page, verify these elements match the design system:

### Layout
- [ ] Page container: `max-w-[1400px] mx-auto px-6 py-8`
- [ ] Header: Sticky, 72px height, correct nav items
- [ ] Page header: Title + subtitle + actions format
- [ ] Grid gaps: `gap-6` (24px)
- [ ] Card columns: Correct `col-span-*` values

### Colors
- [ ] Primary actions: `bg-primary` (#6464f2)
- [ ] Success/Long: `text-emerald-*` or `bg-emerald-*`
- [ ] Danger/Short: `text-red-*` or `bg-red-*`
- [ ] Backgrounds: `bg-white` / `bg-surface-dark`
- [ ] Borders: `border-slate-200` / `border-slate-700`

### Typography
- [ ] Page titles: `text-2xl font-bold tracking-tight`
- [ ] Card titles: `text-lg font-bold`
- [ ] Body text: `text-sm`
- [ ] Labels: `text-xs font-semibold uppercase tracking-wider`
- [ ] Table headers: `text-xs font-semibold uppercase`

### Components
- [ ] Cards: `rounded-2xl shadow-soft p-6`
- [ ] Buttons: `rounded-xl` with correct padding
- [ ] Inputs: `h-10 rounded-xl` with focus states
- [ ] Tables: Rounded header corners, hover rows
- [ ] Badges: Correct color variants and radius

### Icons
- [ ] Using Material Symbols Outlined
- [ ] Default size: 24px
- [ ] Small icons: `text-[18px]` or `text-[14px]`
- [ ] Icon containers: `p-2 bg-primary/10 rounded-lg`

### Dark Mode
- [ ] All backgrounds have dark variants
- [ ] Text colors switch appropriately
- [ ] Borders use `/50` opacity or darker shades
- [ ] Accent backgrounds reduce to `*/10` or `*/30`

### Interactions
- [ ] Hover states on all interactive elements
- [ ] Focus states on inputs and buttons
- [ ] Transitions: `transition-colors` or `transition-all`
- [ ] Status animations: `animate-pulse` where needed

---

## Quick Reference

### Tailwind Classes Cheat Sheet

```
/* Card */
bg-white dark:bg-surface-dark rounded-2xl shadow-soft p-6

/* Button Primary */
bg-primary hover:bg-primary-dark text-white font-semibold py-2.5 px-4 rounded-xl transition-all

/* Button Secondary */
bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 font-medium py-2.5 px-4 rounded-xl hover:bg-slate-50 transition-all

/* Input */
h-10 px-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:border-primary/50 focus:ring-0 transition-colors

/* Table Header */
bg-slate-50 dark:bg-slate-800/50 px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider

/* Badge Success */
px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200

/* Status Dot */
size-2 rounded-full bg-emerald-500
```

---

**End of Design System Specification**
