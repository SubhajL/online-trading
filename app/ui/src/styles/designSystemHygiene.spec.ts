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

describe('Design System Hygiene', () => {
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

  describe('Layout Constraints', () => {
    it('AppShell should use max-w-[1400px] not max-w-[1600px]', () => {
      const file = path.join(SHELL_DIR, 'AppShell.tsx')
      if (!fs.existsSync(file)) return

      const content = readFileContent(file)

      expect(content).toContain('max-w-[1400px]')
      expect(content).not.toContain('max-w-[1600px]')
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
