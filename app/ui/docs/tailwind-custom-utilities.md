# Tailwind Custom Utilities

This document describes custom Tailwind CSS utilities and configuration for the Trading Platform UI.

## Overview

Our Tailwind configuration extends the default theme with custom utilities that map to our [design tokens](./design-tokens.md). This provides a consistent API for styling while maintaining design system constraints.

Configuration file: [`tailwind.config.ts`](../tailwind.config.ts)

## Custom Color Utilities

### Primary Colors

```tsx
<div className="bg-primary-600 text-white">Primary button</div>
<div className="bg-primary-700 text-white">Primary button hover</div>
```

### Text Colors

```tsx
<p className="text-primary">Primary text (#f0f0f0)</p>
<p className="text-secondary">Secondary text (#d1d5db)</p>
<p className="text-muted">Muted text (#9ca3af)</p>
<p className="text-success">Success text (#10b981)</p>
<p className="text-danger">Danger text (#ef4444)</p>
```

### Surface Colors

```tsx
<div className="bg-surface-base">Base background (#1a1d26)</div>
<div className="bg-surface-raised">Raised surface (#2a2d3a)</div>
<div className="bg-surface-overlay">Overlay (#3a3d4a)</div>
<div className="hover:bg-surface-hover">Hover state</div>
```

### Border Colors

```tsx
<div className="border border-subtle">Subtle border</div>
<div className="border border-default">Default border</div>
<input className="focus:ring-2 focus:ring-focus" />
```

## Custom Spacing Utilities

Our spacing scale uses a consistent 4px base. **Important**: Custom spacing utilities are prefixed with `space-` to avoid conflicts with Tailwind's default spacing.

### Spacing Scale

| Class      | Value | Use Case              |
| ---------- | ----- | --------------------- |
| `space-1`  | 4px   | Tight spacing         |
| `space-2`  | 8px   | Small gaps            |
| `space-3`  | 12px  | Compact spacing       |
| `space-4`  | 16px  | Default spacing       |
| `space-5`  | 20px  | Medium spacing        |
| `space-6`  | 24px  | Large spacing         |
| `space-7`  | 32px  | Extra large spacing   |
| `space-8`  | 40px  | Section spacing       |
| `space-9`  | 48px  | Large section spacing |
| `space-10` | 64px  | Page-level spacing    |

### Usage Examples

```tsx
// Padding
<div className="p-space-4">Padding 16px</div>
<div className="px-space-6 py-space-4">Horizontal 24px, Vertical 16px</div>

// Margin
<div className="m-space-4">Margin 16px</div>
<div className="mt-space-8 mb-space-6">Top 40px, Bottom 24px</div>

// Gap (for flexbox/grid)
<div className="flex gap-space-4">Flex with 16px gap</div>
<div className="grid grid-cols-3 gap-space-6">Grid with 24px gap</div>
```

### ⚠️ Important: Spacing Prefix

Custom spacing uses the `space-` prefix to avoid conflicts with Tailwind's default spacing utilities:

```tsx
// ✅ Correct: Custom spacing
<div className="p-space-4 gap-space-6 m-space-8" />

// ✅ Also correct: Tailwind default spacing
<div className="p-4 gap-6 m-8" />

// ❌ Wrong: Mixing without prefix will use Tailwind defaults
<div className="p-4" /> // This is 1rem, not our custom 16px token
```

## Typography Utilities

### Font Sizes

```tsx
<p className="text-xs">Extra small (12px)</p>
<p className="text-sm">Small (14px)</p>
<p className="text-base">Base (16px)</p>
<p className="text-lg">Large (18px)</p>
<p className="text-xl">Extra large (20px)</p>
<p className="text-2xl">2X large (24px)</p>
```

### Font Weights

```tsx
<p className="font-normal">Normal (400)</p>
<p className="font-medium">Medium (500)</p>
<p className="font-semibold">Semibold (600)</p>
<p className="font-bold">Bold (700)</p>
```

### Line Heights

```tsx
<p className="leading-tight">Tight (1.25)</p>
<p className="leading-normal">Normal (1.5)</p>
<p className="leading-relaxed">Relaxed (1.75)</p>
```

## Border Radius Utilities

```tsx
<div className="rounded-sm">Small radius (4px)</div>
<div className="rounded-md">Medium radius (6px)</div>
<div className="rounded-lg">Large radius (8px)</div>
<div className="rounded-full">Circular (9999px)</div>
```

## Shadow Utilities

```tsx
<div className="shadow-sm">Subtle shadow</div>
<div className="shadow-md">Medium shadow</div>
<div className="shadow-lg">Large shadow</div>
```

## Transition Utilities

Custom transition durations that match our design tokens:

```tsx
// Duration
<div className="transition-all duration-fast">150ms</div>
<div className="transition-all duration-base">200ms</div>
<div className="transition-all duration-slow">300ms</div>

// Combined with easing
<button className="transition-colors duration-fast ease-in-out hover:bg-primary-700">
  Smooth hover
</button>
```

## Responsive Design

All utilities support Tailwind's responsive prefixes:

```tsx
<div className="p-space-4 md:p-space-6 lg:p-space-8">
  Responsive padding
</div>

<div className="text-sm md:text-base lg:text-lg">
  Responsive font size
</div>

<div className="bg-surface-base md:bg-surface-raised">
  Responsive background
</div>
```

## Common Patterns

### Cards

```tsx
<div className="bg-surface-raised border border-subtle rounded-md p-space-6 shadow-sm">
  Card content
</div>
```

### Buttons

```tsx
// Primary button
<button className="bg-primary-600 hover:bg-primary-700 text-white px-space-4 py-space-2 rounded-md transition-colors duration-fast">
  Primary Button
</button>

// Secondary button
<button className="bg-surface-raised hover:bg-surface-hover text-primary border border-subtle px-space-4 py-space-2 rounded-md transition-all duration-fast">
  Secondary Button
</button>

// Danger button
<button className="bg-danger hover:bg-red-700 text-white px-space-4 py-space-2 rounded-md transition-colors duration-fast">
  Delete
</button>
```

### Navigation Links

```tsx
<Link
  href="/dashboard"
  className="text-muted hover:text-primary transition-colors duration-fast"
>
  Dashboard
</Link>

// Active state
<Link
  href="/dashboard"
  className="text-primary font-medium border-b-2 border-primary"
>
  Dashboard
</Link>
```

### Form Inputs

```tsx
<input
  type="text"
  className="bg-surface-raised border border-subtle rounded-md px-space-4 py-space-2 text-primary focus:border-focus focus:ring-2 focus:ring-focus transition-all duration-fast"
  placeholder="Enter text..."
/>
```

### Modals

```tsx
<div className="fixed inset-0 bg-black/50 flex items-center justify-center z-modal">
  <div className="bg-surface-raised rounded-lg shadow-lg p-space-6 max-w-md w-full">
    <h2 className="text-xl font-semibold mb-space-4">Modal Title</h2>
    <p className="text-secondary mb-space-6">Modal content</p>
    <div className="flex gap-space-4 justify-end">
      <button className="px-space-4 py-space-2 rounded-md border border-subtle">Cancel</button>
      <button className="px-space-4 py-space-2 rounded-md bg-primary-600 text-white">
        Confirm
      </button>
    </div>
  </div>
</div>
```

## Accessibility Utilities

### Focus Visible

```tsx
<button className="focus-visible:ring-2 focus-visible:ring-focus focus-visible:outline-none">
  Keyboard accessible button
</button>
```

### Screen Reader Only

```tsx
<span className="sr-only">Screen reader only text</span>
```

### Touch Targets

Ensure minimum 44px touch targets for mobile:

```tsx
<button className="min-h-[44px] px-space-4">Mobile-friendly button</button>
```

## Dark Mode Support

Currently, the app uses a dark theme by default. To add light mode support in the future:

```tsx
<div className="bg-surface-base dark:bg-gray-900">Content</div>
```

## Configuration Reference

To modify or extend the Tailwind configuration:

1. Edit `tailwind.config.ts`
2. Ensure new utilities map to design tokens in `src/styles/tokens.css`
3. Update this documentation
4. Run type checking: `pnpm typecheck`

Example of adding a new color:

```typescript
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: {
        warning: {
          500: 'var(--color-warning-500)',
          600: 'var(--color-warning-600)',
        },
      },
    },
  },
}
```

```css
/* src/styles/tokens.css */
:root {
  --color-warning-500: #f59e0b;
  --color-warning-600: #d97706;
}
```

## Best Practices

1. **Always use design tokens**: Avoid hardcoded values like `bg-[#1a1d26]`
2. **Prefer semantic utilities**: Use `text-primary` instead of `text-gray-100`
3. **Use custom spacing prefix**: Remember `space-` prefix for custom spacing
4. **Maintain WCAG compliance**: Ensure sufficient contrast ratios
5. **Test responsive behavior**: Always test on mobile, tablet, and desktop
6. **Use transitions**: Add smooth transitions for interactive elements

## Related Documentation

- [Design Tokens](./design-tokens.md) - Complete design token reference
- [Tailwind CSS Documentation](https://tailwindcss.com/docs) - Official Tailwind docs
- [WCAG Guidelines](https://www.w3.org/WAI/WCAG21/quickref/) - Accessibility standards
