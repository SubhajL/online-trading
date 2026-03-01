import { test as base, expect } from '@playwright/test'
import type { Page, BrowserContext } from '@playwright/test'

export type AuthFixtures = {
  authenticatedPage: Page
  adminPage: Page
  guestPage: Page
}

export const authTest = base.extend<AuthFixtures>({
  // Regular authenticated user
  authenticatedPage: async ({ browser }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()

    // Perform login
    await page.goto('/login')
    
    // Check if login form exists
    const loginForm = page.locator('form[data-testid="login-form"]')
    if (await loginForm.isVisible({ timeout: 5000 })) {
      await page.fill('[data-testid="email-input"]', 'test@example.com')
      await page.fill('[data-testid="password-input"]', 'password123')
      await page.click('[data-testid="login-button"]')
      
      // Wait for successful login
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
    } else {
      // If no login required, just navigate to dashboard
      await page.goto('/dashboard')
    }

    await use(page)
    await context.close()
  },

  // Admin user with elevated privileges
  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      // Load admin auth state if it exists
      storageState: 'tests/auth/admin-auth.json'
    })
    const page = await context.newPage()

    // Navigate to admin area
    await page.goto('/admin')
    
    // Verify admin access
    const adminPanel = page.locator('[data-testid="admin-panel"]')
    if (await adminPanel.isVisible({ timeout: 5000 })) {
      console.log('✅ Admin access verified')
    } else {
      // Fallback: perform admin login
      await page.goto('/admin/login')
      await page.fill('[data-testid="admin-username"]', 'admin')
      await page.fill('[data-testid="admin-password"]', 'admin123')
      await page.click('[data-testid="admin-login-btn"]')
      
      await expect(page.locator('[data-testid="admin-panel"]')).toBeVisible({ timeout: 10000 })
    }

    await use(page)
    await context.close()
  },

  // Guest user (no authentication)
  guestPage: async ({ browser }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()

    // Clear any existing auth
    await context.clearCookies()
    await context.clearPermissions()

    await use(page)
    await context.close()
  },
})

export { expect } from '@playwright/test'

// Helper functions for authentication testing
export class AuthHelpers {
  static async login(page: Page, email: string, password: string) {
    await page.goto('/login')
    await page.fill('[data-testid="email-input"]', email)
    await page.fill('[data-testid="password-input"]', password)
    await page.click('[data-testid="login-button"]')
    
    // Wait for login to complete
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
  }

  static async logout(page: Page) {
    await page.click('[data-testid="user-menu"]')
    await page.click('[data-testid="logout-button"]')
    
    // Wait for logout to complete
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 10000 })
  }

  static async expectAuthenticated(page: Page) {
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible()
  }

  static async expectUnauthenticated(page: Page) {
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible()
  }

  static async expectAdminAccess(page: Page) {
    await expect(page.locator('[data-testid="admin-panel"]')).toBeVisible()
  }
}
