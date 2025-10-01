# Design Tokens

This document describes the design token system used in the Trading Platform UI.

## Overview

Design tokens are centralized design decisions stored as CSS custom properties. They ensure consistency across the application and make it easy to update the design system globally.

All tokens are defined in [`src/styles/tokens.css`](../src/styles/tokens.css).

## Token Categories

### Colors

#### Primary Colors

- `--color-primary-600`: Main brand color (emerald green)
- `--color-primary-700`: Darker brand color for hover states

#### Text Colors

- `--color-text-primary`: Primary text color (#f0f0f0)
- `--color-text-secondary`: Secondary text color (#d1d5db)
- `--color-text-muted`: Muted text color (#9ca3af)
- `--color-text-success`: Success text color (#10b981)
- `--color-text-danger`: Error/danger text color (#ef4444)

#### Surface Colors

- `--color-surface-base`: Base background (#1a1d26)
- `--color-surface-raised`: Elevated surface (#2a2d3a)
- `--color-surface-overlay`: Modal/overlay background (#3a3d4a)
- `--color-surface-hover`: Hover state background

#### Border Colors

- `--color-border-subtle`: Subtle borders (#3a3d4a)
- `--color-border-default`: Default borders (#4a4d5a)
- `--color-border-focus`: Focus ring color (#10b981)

### Navigation Tokens

Navigation-specific tokens ensure consistent styling across Header and Sidebar components:

- `--nav-text`: Default navigation link color
- `--nav-text-hover`: Navigation link hover color
- `--nav-text-active`: Active navigation link color
- `--nav-indicator`: Active indicator/underline color (#10b981)
- `--nav-active-bg`: Active state background (transparent green)
- `--nav-active-shadow`: Active state shadow/glow

### Spacing

Spacing tokens use a consistent 4px base scale:

- `--space-1`: 4px
- `--space-2`: 8px
- `--space-3`: 12px
- `--space-4`: 16px
- `--space-5`: 20px
- `--space-6`: 24px
- `--space-7`: 32px
- `--space-8`: 40px
- `--space-9`: 48px
- `--space-10`: 64px

### Typography

#### Font Sizes

- `--font-size-xs`: 0.75rem (12px)
- `--font-size-sm`: 0.875rem (14px)
- `--font-size-base`: 1rem (16px)
- `--font-size-lg`: 1.125rem (18px)
- `--font-size-xl`: 1.25rem (20px)
- `--font-size-2xl`: 1.5rem (24px)

#### Font Weights

- `--font-weight-normal`: 400
- `--font-weight-medium`: 500
- `--font-weight-semibold`: 600
- `--font-weight-bold`: 700

#### Line Heights

- `--line-height-tight`: 1.25
- `--line-height-normal`: 1.5
- `--line-height-relaxed`: 1.75

### Border Radius

- `--radius-sm`: 0.25rem (4px)
- `--radius-md`: 0.375rem (6px)
- `--radius-lg`: 0.5rem (8px)
- `--radius-full`: 9999px (circular)

### Shadows

- `--shadow-sm`: Subtle shadow for cards
- `--shadow-md`: Medium shadow for elevated elements
- `--shadow-lg`: Large shadow for modals/dropdowns

### Z-Index

- `--z-index-dropdown`: 1000
- `--z-index-sticky`: 1020
- `--z-index-fixed`: 1030
- `--z-index-modal-backdrop`: 1040
- `--z-index-modal`: 1050
- `--z-index-popover`: 1060
- `--z-index-tooltip`: 1070

### Transitions

- `--duration-fast`: 150ms
- `--duration-base`: 200ms
- `--duration-slow`: 300ms
- `--easing-default`: cubic-bezier(0.4, 0, 0.2, 1)

### Accessibility

- `--touch-target-min`: 44px (minimum touch target size for WCAG AA)

## Usage

### In CSS

```css
.my-component {
  background: var(--color-surface-raised);
  color: var(--color-text-primary);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  transition: background var(--duration-fast) var(--easing-default);
}

.my-component:hover {
  background: var(--color-surface-hover);
}
```

### With Tailwind CSS

Our Tailwind configuration maps design tokens to utility classes. See [tailwind-custom-utilities.md](./tailwind-custom-utilities.md) for details.

```jsx
<div className="bg-surface-raised text-primary p-4 rounded-md">Content</div>
```

### In React Components

Use Tailwind utilities that reference tokens, or use inline styles for dynamic values:

```tsx
// Preferred: Use Tailwind utilities
<button className="bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-md">
  Button
</button>

// Alternative: CSS-in-JS with tokens
<div style={{
  background: 'var(--color-surface-raised)',
  padding: 'var(--space-4)'
}}>
  Content
</div>
```

## WCAG Compliance

All color tokens are designed to meet WCAG AA contrast requirements:

- **Text on backgrounds**: Minimum 4.5:1 contrast ratio
- **Large text (18pt+)**: Minimum 3:1 contrast ratio
- **Touch targets**: Minimum 44px × 44px (see `--touch-target-min`)

## Navigation Token Usage

The navigation tokens ensure consistent active states across Header and Sidebar:

```css
.nav-link {
  color: var(--nav-text);
  transition: color var(--duration-fast);
}

.nav-link:hover {
  color: var(--nav-text-hover);
}

.nav-link.active {
  color: var(--nav-text-active);
  background: var(--nav-active-bg);
  box-shadow: 0 0 0 3px var(--nav-active-shadow);
}

.nav-link.active::after {
  background: var(--nav-indicator);
}
```

## Adding New Tokens

When adding new tokens:

1. Define in `src/styles/tokens.css`
2. Use semantic names (describe purpose, not value)
3. Update Tailwind config if needed
4. Document here
5. Ensure WCAG compliance for color tokens

Example:

```css
/* tokens.css */
:root {
  --color-warning-500: #f59e0b;
  --color-warning-600: #d97706;
}
```

```js
// tailwind.config.ts
colors: {
  warning: {
    500: 'var(--color-warning-500)',
    600: 'var(--color-warning-600)',
  }
}
```

## References

- [Design Tokens Community Group](https://www.w3.org/community/design-tokens/)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Material Design Color System](https://material.io/design/color/the-color-system.html)
