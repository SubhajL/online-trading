# Google Stitch Exports (Reference Artifacts)

This folder stores Google Stitch exports for the UI revamp as **reference artifacts** (not production code).

## Structure

- `exports/` — raw `.zip` exports from Stitch (kept as source archives)
- `extracted/` — each zip extracted into a folder containing:
  - `screen.png` (rendered frame)
  - `code.html` (Stitch-generated markup)

## Prompt → Route Mapping

| Prompt         | Extracted folder                       | Intended UI route | Notes                                                                        |
| -------------- | -------------------------------------- | ----------------- | ---------------------------------------------------------------------------- |
| 0 — Styleboard | `extracted/stitch-prompt0-styleboard/` | N/A               | Visual DNA (palette/typography/radii/lines); implement once as tokens/theme. |
| 1 — App Shell  | `extracted/stitch-prompt1-appshell/`   | N/A               | Global layout (topbar/sidebar/footer); implement once as shared shell.       |
| 2 — Dashboard  | `extracted/stitch-prompt2-dashboard/`  | `/`               | Monitoring console / bento grid.                                             |
| 3 — Execution  | `extracted/stitch-prompt3-execution/`  | `/trades`         | Order ticket + lifecycle + market view.                                      |
| 4 — Portfolio  | `extracted/stitch-prompt4-portfolio/`  | `/portfolio`      | Positions/allocations overview.                                              |
| 5 — History    | `extracted/stitch-prompt5-history/`    | `/history`        | Filled orders/trades + filters + detail drawer.                              |
| 6 — Analytics  | `extracted/stitch-prompt6-analytics/`  | `/analytics`      | Performance KPIs + charts.                                                   |
| 7 — Settings   | `extracted/stitch-prompt7-settings/`   | `/settings`       | Preferences + danger zone.                                                   |
| 8 — Login      | `extracted/stitch-prompt8-login/`      | `/login`          | Auth entry + trust cues.                                                     |

## How to use these exports

1. Use Prompt 0 and Prompt 1 as the consistency baseline (tokens + shell).
2. Use each page’s `screen.png` + `code.html` as a scaffold for layout and component inventory.
3. Translate the scaffold into the Next.js UI codebase (`app/ui/src`) using existing design tokens and components (avoid copy-pasting generated HTML into production).

## Versioning policy

- Commit extracted artifacts only (`screen.png` and `code.html` under `extracted/`).
- Do not commit raw zip exports to this repository.
