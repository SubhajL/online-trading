# Comprehensive Style Guidelines

## 1. Purpose & Audience
- Establish a single source of truth for visual design across products, platforms, and teams.
- Provide AI-assisted agents and humans with actionable standards for building and reviewing UI.
- Maintain a cohesive, modern, and accessible experience as features scale.

## 2. Foundational Principles
- **Consistency**: Reuse tokens, components, and patterns; avoid ad hoc styling.
- **Clarity**: Prioritize readability, hierarchy, and straightforward affordances.
- **Accessibility**: Meet WCAG 2.1 AA contrast, focus, and interaction requirements.
- **Scalability**: Design with responsive layouts, reusable tokens, and theming in mind.
- **Performance**: Favor lightweight assets, efficient CSS, and minimal render cost.

## 3. Design System Framework
- Use a modern design system inspired by Google Material Design for structure, spacing, and responsive grid guidance.
- Implement tokens via Tailwind CSS (or an equivalent utility-first framework) for rapid adoption; extend the config with custom tokens defined in this guide.
- When a team already has an opinionated system, map these guidelines onto existing primitives rather than duplicating effort.

## 4. Visual Identity Foundations
### 4.1 Color Strategy
- Define a primary brand color for high-emphasis actions, a secondary neutral, and an accent for occasional highlights.
- Supplement with neutrals and functional status colors to cover all UI needs.
- Maintain consistent role-based usage (primary = main actions, success = confirmations, etc.).

**Default Palette (customize to fit brand DNA):**

| Token | Hex | Usage Guidance |
| --- | --- | --- |
| `primary-600` | #6C5CE7 | Primary buttons, active states, key highlights |
| `primary-700` | #5936E0 | Hover/pressed state for primary elements |
| `secondary-800` | #4B5563 | Secondary actions, text on dark surfaces |
| `accent-500` | #14B8A6 | Links, subtle highlights, data viz accents |
| `neutral-100` | #F9FAFB | Backgrounds, panels |
| `neutral-300` | #D1D5DB | Borders, dividers |
| `neutral-500` | #9CA3AF | Disabled text, secondary labels |
| `neutral-900` | #111827 | Primary text |
| `success-500` | #22C55E | Success states |
| `warning-500` | #F59E0B | Warning states |
| `error-500` | #EF4444 | Error states |
| `white` | #FFFFFF | Text on dark backgrounds, cards |

- Validate foreground/background ratios; primary-on-white and white-on-primary should exceed 4.5:1 contrast.
- Provide light/dark variants when theming requires additional depth.

### 4.2 Typography & Hierarchy
- Primary font: Inter (or similar high-legibility sans-serif); fall back to system fonts.
- Typographic scale (adjustable per platform):
  - H1: 32px, bold
  - H2: 24px, semibold
  - H3: 20px, semibold
  - Body: 16px, regular
  - Small: 14px, regular
- Use sentence case for most UI copy; reserve ALL CAPS for tokens or short labels.
- Maintain 1.4–1.6 line-height for paragraphs and generous spacing around headings.

### 4.3 Branding & Logo Usage
- Keep wordmarks simple, legible, and scalable; reserve decorative typography for marketing collateral.
- Provide monochrome and full-color versions; ensure minimum clearspace equals logo height’s 25% on all sides.
- Do not alter proportions, colors, or add shadows beyond defined variants.

## 5. Core Design Tokens
Define tokens centrally (CSS custom properties, Tailwind theme extensions, or design tool styles).

```css
:root {
  /* Color */
  --color-primary: #6C5CE7;
  --color-primary-dark: #5936E0;
  --color-secondary: #4B5563;
  --color-accent: #14B8A6;
  --color-neutral-100: #F9FAFB;
  --color-neutral-300: #D1D5DB;
  --color-neutral-500: #9CA3AF;
  --color-neutral-900: #111827;
  --color-success: #22C55E;
  --color-warning: #F59E0B;
  --color-error: #EF4444;
  --color-white: #FFFFFF;

  /* Spacing (8px base with 4px half-step) */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  /* Sizing */
  --size-icon-sm: 16px;
  --size-icon-md: 24px;
  --size-icon-lg: 32px;
  --size-input-height: 40px;
  --size-button-height: 40px;

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --radius-pill: 999px;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.12);
  --shadow-md: 0 4px 8px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 16px rgba(0,0,0,0.10);

  /* Motion */
  --anim-fast: 150ms ease;
  --anim-medium: 250ms ease;
  --anim-slow: 400ms ease;

  /* Breakpoints */
  --bp-sm: 640px;
  --bp-md: 768px;
  --bp-lg: 1024px;
  --bp-xl: 1280px;
}
```

- Store tokens in code and design tools; run linting or automated checks to detect drift.
- Use the 12-column responsive grid (12 desktop, 8 tablet, 4 mobile) with consistent gutters aligned to the 8px rhythm.

## 6. Component Standards
### 6.1 Buttons
- Hierarchy: primary (solid), secondary (outlined or neutral), tertiary (text/icon only).
- Default padding: 8px vertical × 16px horizontal; maintain minimum 44px touch target on touch devices.
- States: hover (darken or elevate), active (pressed feedback), focus (visible outline), disabled (reduced opacity, no shadow).
- Icons align left with 8px spacing; avoid standalone icon buttons without accessible labels.

### 6.2 Form Inputs
- Structure: top-aligned labels, 1px neutral border, 4px radius, 8px vertical spacing between fields.
- Focus: primary-colored border and ring; maintain accessible focus outlines even when using custom styling.
- Validation: surface error text beneath field using error color; optional success border for actions requiring confirmation.
- Inputs stretch to container width on small screens; never less than 280px on desktop for readability.

### 6.3 Modals & Overlays
- Overlay: rgba(0,0,0,0.5) backdrop covering viewport; lock background scroll when open.
- Container: white background, 16px radius, `--shadow-lg`, 24px padding, max-width ~600px desktop, 90% viewport width mobile.
- Structure: title (H3), body content, footer with primary + secondary actions right-aligned.
- Enter/exit animation: fade + 4% scale in `--anim-medium`.

### 6.4 Alerts & Notifications
- Use status colors with light-tint backgrounds and darker text/icons.
- Layout: icon (20px) + message; 12px vertical padding, 16px horizontal, 4px radius, optional colored border-left.
- Toasts stack vertically with 8px gap; auto-dismiss after 5–7s and remain dismissible.

### 6.5 Navigation
- Top navigation height ~60px desktop, 50px mobile; include logo, primary nav, user actions.
- If using colored header, ensure text/icons contrast at ≥4.5:1; provide focus indicators for keyboard navigation.
- Mobile: collapse links into accessible menu; use motion tokens for slide/fade transitions.
- Sticky headers require subtle shadow (`--shadow-sm`) to separate content.

### 6.6 Cards & Panels
- Background white or neutral-100, 8px radius, `--shadow-sm` or 1px border neutral-200.
- Internal padding: 16–24px; consistent spacing between header, body, footer.
- Hover (if interactive): elevate to `--shadow-md` or adjust border color; add smooth transition.

### 6.7 Data Tables
- Header row: neutral-100 background, bold text, 12px vertical padding.
- Row striping optional with neutral-50; maintain 16px minimum cell padding.
- Use overflow patterns for long content; provide responsive stacking or horizontal scroll on small screens.

### 6.8 Supporting Elements
- **Tooltips**: dark background, white text, 4px radius, 150ms fade.
- **Dropdowns**: white surface, `--shadow-sm`, 4px radius, 8px vertical padding per item.
- **Loaders**: use primary or accent color; avoid blocking interactions when possible.
- **Iconography**: adopt a unified icon set (stroke or filled); size to 16/20/24px increments and align to pixel grid.

## 7. Accessibility & Inclusivity
- Enforce WCAG 2.1 AA contrast on text and interactive elements.
- Provide visible focus states distinct from hover states.
- Support keyboard-only navigation; ensure logical tab order and role attributes.
- Supply descriptive alt text for imagery and `aria-label`/`aria-describedby` for icons or controls lacking text.
- Avoid conveying meaning with color alone; add icons or labels to reinforce state.

## 8. Interaction & Motion
- Use motion to reinforce spatial relationships, not to distract.
- Keep durations between 150–300ms; use easing tailored to motion type (ease-out for exits, ease-in for entries).
- Provide reduced-motion alternatives using `prefers-reduced-motion` media queries.

## 9. Layout & Responsiveness
- Base spacing on 8px grid; prefer multiples of 4px only for tight adjustments.
- Use responsive breakpoints to adjust layout:
  - ≥1280px (xl): max content width 1200px centered.
  - 1024–1279px (lg): two-column layouts collapse to 8-column grid.
  - 768–1023px (md): stack complex layouts, increase vertical spacing.
  - ≤767px (sm): single-column flow, full-width interactive elements.
- Maintain consistent gutters (16–24px) and vertical rhythm across breakpoints.

## 10. Implementation Guidance
- Extend Tailwind (or equivalent) theme with tokens above; avoid inline hex values or arbitrary spacing utilities.
- Use component primitives (e.g., button, card) that consume tokens by default; expose variants for state changes only.
- Document patterns in Storybook or an equivalent catalog; keep usage notes synchronized with code.
- Automate linting for disallowed colors, spacing, or typography to catch drift early.

## 11. AI-Assisted Build Checklist
- Confirm new components use defined tokens (colors, spacing, type).
- Verify hierarchy: primary action visually dominant, supporting actions secondary.
- Check responsive behavior at sm/md/lg breakpoints; ensure touch targets ≥44px.
- Validate accessibility: contrast, focus, semantics, and ARIA roles.
- Ensure motion, shadows, and radii align with tokens; no custom values without approval.

## 12. AI-Assisted Review Checklist
- Does the change reuse existing components or introduce redundant variants?
- Are tokens or colors hard-coded instead of referenced? Flag and revert to token usage.
- Are typography levels consistent with scale and content hierarchy?
- Do interactive states (hover, focus, disabled, active) align with definitions?
- Are alerts, validation messages, and feedback using the correct status colors and iconography?
- Are modals, panels, and overlays following structural and spacing guidelines?
- If anomalies exist, recommend updates to tokens or documentation before approving.

## 13. Governance & Maintenance
- Review tokens quarterly; log additions/removals and communicate to design and engineering teams.
- Centralize decisions via a design system working group (design, engineering, product, accessibility).
- Version the style guide; update semantic tags (e.g., v1.1) and summarize notable changes.
- Archive deprecated patterns and provide migration paths to prevent drift.


# Comprehensive Style Guidelines (SOTA 2025 Integrated)

## 1. Foundational Principles
- **Single Source of Truth**: Every design decision—from spacing to shadow opacity—must be tokenized and synced between Figma and code.
- **Consistency & Scalability**: Reuse components; design with responsive tokens that adapt across all platform breakpoints.

## 2. Visual Identity & SOTA Aesthetics

### 2.1 Color Strategy (Material You & Dynamic Theming)
- **Primary actions**: `primary-600` (#6C5CE7) or dynamic AI-adaptive palettes.
- **Dark Mode**: Prioritize high-contrast dark modes to reduce eye strain and energy consumption on OLED screens.
- **Glassmorphism Layering**: Use "Liquid Glass" materials—translucent, dynamic surfaces—to unify navigation and modals.

| Token | Hex | SOTA Usage |
| --- | --- | --- |
| `primary-600` | #6C5CE7 | Main CTA, Active States |
| `accent-500` | #14B8A6 | Links, Data Viz Highlights |
| `neutral-900` | #111827 | Primary Text |
| `success-500` | #22C55E | Confirmation States |

### 2.2 Typography & SOTA Scalability
- **Variable Fonts**: Use Inter or system fonts that dynamically adjust weight for readability.
- **Scale**: H1 (32px), H2 (24px), Body (16px), Small (14px).
- **Data Expression**: Use monospaced fonts for technical data values to ensure alignment and clarity.

## 3. Component Standards (SOTA Enhanced)

### 3.1 Buttons & Inputs
- **Hierarchy**: Primary (solid), Secondary (outline), Tertiary (text), Destructive (error).
- **Touch Targets**: Minimum 44px for touch-enabled devices.
- **Validation**: Surface real-time AI-assisted error correction beneath fields.

### 3.2 Modals & Bento-Panels
- **Container**: White or neutral-100, 16px radius, `--shadow-lg`.
- **Bento Integration**: Use modular bento-style cards with 18px rounded corners to organize complex dashboards.

### 3.3 Navigation & Layout
- **Sticky Headers**: Use `--shadow-sm` and background blurs (Glassmorphism) to separate from content.
- **Responsive Grid**: 12-column (Desktop), 8-column (Tablet), 4-column (Mobile) aligned to the 8px rhythm.

## 4. Interaction & Motion
- **Timing**: 150ms-300ms duration with physics-informed easing.
- **Proactive Motion**: Use subtle animations to reinforce spatial relationships and anticipate user next-steps.

## 5. Governance & AI Review
- **AI Build Checklist**: Verify that all new components consume tokens, meet WCAG 2.2 AA contrast, and maintain 100% resource alignment.
- **Design-to-Code Bridge**: Use automated sync tools (e.g., GitHub Actions) to catch token drift early.

---
Use this document as the authoritative reference for styling decisions. When exceptions are needed, document rationale and plan for follow-up so the system stays cohesive over time.
