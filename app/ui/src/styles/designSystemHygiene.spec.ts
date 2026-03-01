/**
 * Design System Hygiene Tests
 *
 * These tests ensure design system consistency by detecting drift from spec.
 * They fail if deprecated patterns (text-[11px], non-gap-6, inline shadows) are reintroduced.
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

const DASHBOARD_DIR = path.resolve(__dirname, '../components/Dashboard')
const SHELL_DIR = path.resolve(__dirname, '../components/shell')

function readFileContent(filePath: string): string {
  return fs.readFileSync(filePath, 'utf-8')
}

function getFilesInDir(dir: string, extension: string): string[] {
  if (!fs.existsSync(dir)) return []
  return fs
    .readdirSync(dir)
    .filter(f => f.endsWith(extension) && !f.includes('.spec.'))
    .map(f => path.join(dir, f))
}

const SRC_DIR = path.resolve(__dirname, '..')

function getAllTsxFiles(dir: string): string[] {
  const results: string[] = []
  if (!fs.existsSync(dir)) return results

  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      results.push(...getAllTsxFiles(fullPath))
    } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.spec.')) {
      results.push(fullPath)
    }
  }
  return results
}

describe('Design System Hygiene', () => {
  describe('Icon Library', () => {
    it('should not import from lucide-react anywhere in src/', () => {
      const allTsxFiles = getAllTsxFiles(SRC_DIR)
      const violations: string[] = []

      for (const file of allTsxFiles) {
        const content = readFileContent(file)
        if (content.includes("from 'lucide-react'")) {
          violations.push(path.relative(SRC_DIR, file))
        }
      }

      expect(
        violations,
        `Files still importing lucide-react (must use MaterialIcon): ${violations.join(', ')}`,
      ).toEqual([])
    })
  })

  describe('Label Typography', () => {
    it('dashboard components should use text-xs not text-[11px]', () => {
      const dashboardFiles = getFilesInDir(DASHBOARD_DIR, '.tsx')
      const violations: string[] = []

      for (const file of dashboardFiles) {
        const content = readFileContent(file)
        if (content.includes('text-[11px]')) {
          violations.push(path.basename(file))
        }
      }

      expect(violations, `Files still using text-[11px]: ${violations.join(', ')}`).toEqual([])
    })

    it('shell components should use text-xs not text-[11px]', () => {
      const shellFiles = getFilesInDir(SHELL_DIR, '.tsx')
      const violations: string[] = []

      for (const file of shellFiles) {
        const content = readFileContent(file)
        if (content.includes('text-[11px]')) {
          violations.push(path.basename(file))
        }
      }

      expect(violations, `Files still using text-[11px]: ${violations.join(', ')}`).toEqual([])
    })
  })

  describe('Dashboard Grid Gaps', () => {
    it('MonitoringDashboard should use gap-6 for main layout gaps', () => {
      const file = path.join(DASHBOARD_DIR, 'MonitoringDashboard.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      // Main dashboard container should use gap-6
      expect(content).toContain('gap-6')
      // Should not have gap-8 in main container
      expect(content).not.toMatch(/className="[^"]*flex[^"]*gap-8/)
    })
  })

  describe('Shadow Tokens', () => {
    it('dashboard cards should use shadow-soft token not inline shadows', () => {
      const dashboardFiles = getFilesInDir(DASHBOARD_DIR, '.tsx')
      const inlineShadowPattern = /shadow-\[0_4px_20px_-2px_rgba\(0,0,0,0\.05\)\]/

      const violations: string[] = []

      for (const file of dashboardFiles) {
        const content = readFileContent(file)
        if (inlineShadowPattern.test(content)) {
          violations.push(path.basename(file))
        }
      }

      expect(
        violations,
        `Files using inline shadow instead of shadow-soft: ${violations.join(', ')}`,
      ).toEqual([])
    })
  })

  describe('Primitive Sizing', () => {
    const UI_DIR = path.resolve(__dirname, '../components/ui')

    it('Input should use h-10 rounded-xl and dark background', () => {
      const file = path.join(UI_DIR, 'input.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toContain('h-10')
      expect(content).toContain('rounded-xl')
      expect(content).toContain('dark:bg-slate-800')
      expect(content).toContain('dark:border-slate-700')
    })

    it('SelectTrigger should use h-10 rounded-xl and dark background', () => {
      const file = path.join(UI_DIR, 'select.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toContain('h-10')
      expect(content).toContain('rounded-xl')
      expect(content).toContain('dark:bg-slate-800')
    })

    it('TableHeader should have dark background token', () => {
      const file = path.join(UI_DIR, 'table.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toMatch(/dark:bg-slate-800/)
    })
  })

  describe('Layout Constraints', () => {
    it('AppShell should use max-w-[1400px] not max-w-[1600px]', () => {
      const file = path.join(SHELL_DIR, 'AppShell.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toContain('max-w-[1400px]')
      expect(content).not.toContain('max-w-[1600px]')
    })

    it('AppShell should not render desktop AppSidebar (only MobileSidebar)', () => {
      const file = path.join(SHELL_DIR, 'AppShell.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      // Should import MobileSidebar only, not AppSidebar directly
      expect(content).toContain("import { MobileSidebar } from './AppSidebar'")
      // Should not have <AppSidebar in render output
      expect(content).not.toMatch(/<AppSidebar\s/)
    })

    it('AppTopbar should use h-18 (72px) not h-14 (56px)', () => {
      const file = path.join(SHELL_DIR, 'AppTopbar.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toMatch(/\bh-18\b/)
      expect(content).not.toMatch(/\bh-14\b/)
    })
  })
})
