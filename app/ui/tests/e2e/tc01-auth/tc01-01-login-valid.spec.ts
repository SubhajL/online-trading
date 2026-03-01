import { authTest as test, expect, AuthHelpers } from '../../fixtures/auth.fixture'

test.describe('TC01.01: Login with Valid Credentials', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing auth state
    await page.context().clearCookies()
    await page.context().clearPermissions()
  })

  test('should login successfully with valid email and password', async ({ page }) => {
    await page.goto('/login')

    // Verify login form is visible
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible()

    // Fill valid credentials
    await page.fill('[data-testid="email-input"]', 'test@example.com')
    await page.fill('[data-testid="password-input"]', 'password123')

    // Submit form
    await page.click('[data-testid="login-button"]')

    // Verify successful login
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
    
    // Verify redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard/)

    // Verify user info is displayed
    await expect(page.locator('[data-testid="user-email"]')).toContainText('test@example.com')
  })

  test('should remember login state after page refresh', async ({ page }) => {
    // Login first
    await AuthHelpers.login(page, 'test@example.com', 'password123')

    // Refresh the page
    await page.reload()

    // Verify still logged in
    await AuthHelpers.expectAuthenticated(page)
    await expect(page.locator('[data-testid="user-email"]')).toContainText('test@example.com')
  })

  test('should handle Enter key submission', async ({ page }) => {
    await page.goto('/login')

    await page.fill('[data-testid="email-input"]', 'test@example.com')
    await page.fill('[data-testid="password-input"]', 'password123')

    // Press Enter instead of clicking button
    await page.press('[data-testid="password-input"]', 'Enter')

    // Verify successful login
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
  })

  test('should show loading state during login', async ({ page }) => {
    // Mock slow login response
    await page.route('**/api/auth/login', async (route) => {
      await new Promise(resolve => setTimeout(resolve, 2000)) // 2 second delay
      await route.continue()
    })

    await page.goto('/login')
    await page.fill('[data-testid="email-input"]', 'test@example.com')
    await page.fill('[data-testid="password-input"]', 'password123')
    await page.click('[data-testid="login-button"]')

    // Verify loading state
    await expect(page.locator('[data-testid="login-loading"]')).toBeVisible()
    await expect(page.locator('[data-testid="login-button"]')).toBeDisabled()

    // Wait for login to complete
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 15000 })
  })

  test('should handle keyboard navigation', async ({ page }) => {
    await page.goto('/login')

    // Tab through form elements
    await page.keyboard.press('Tab') // Focus email input
    await page.keyboard.type('test@example.com')

    await page.keyboard.press('Tab') // Focus password input
    await page.keyboard.type('password123')

    await page.keyboard.press('Tab') // Focus login button
    await page.keyboard.press('Enter') // Submit

    // Verify successful login
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
  })

  test('should clear form validation errors on successful login', async ({ page }) => {
    await page.goto('/login')

    // First, trigger validation errors
    await page.click('[data-testid="login-button"]')
    await expect(page.locator('[data-testid="email-error"]')).toBeVisible()

    // Then fill valid data and submit
    await page.fill('[data-testid="email-input"]', 'test@example.com')
    await page.fill('[data-testid="password-input"]', 'password123')
    await page.click('[data-testid="login-button"]')

    // Verify errors are cleared and login succeeds
    await expect(page.locator('[data-testid="email-error"]')).not.toBeVisible()
    await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })
  })

  test('should handle different valid email formats', async ({ page }) => {
    const validEmails = [
      'user@domain.com',
      'user.name@domain.com',
      'user+tag@domain.co.uk',
      'user123@sub.domain.org'
    ]

    for (const email of validEmails) {
      await page.goto('/login')
      await page.fill('[data-testid="email-input"]', email)
      await page.fill('[data-testid="password-input"]', 'password123')
      await page.click('[data-testid="login-button"]')

      // Verify login succeeds for each email format
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible({ timeout: 10000 })

      // Logout for next iteration
      await AuthHelpers.logout(page)
    }
  })

  test('should redirect to intended page after login', async ({ page }) => {
    // Try to access protected page while not logged in
    await page.goto('/trading/BTCUSDT')

    // Should redirect to login with return URL
    await expect(page).toHaveURL(/\/login.*returnUrl/)

    // Login
    await page.fill('[data-testid="email-input"]', 'test@example.com')
    await page.fill('[data-testid="password-input"]', 'password123')
    await page.click('[data-testid="login-button"]')

    // Should redirect back to intended page
    await expect(page).toHaveURL(/\/trading\/BTCUSDT/)
  })
})
