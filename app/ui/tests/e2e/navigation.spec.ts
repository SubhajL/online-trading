import { test, expect } from '@playwright/test'

test.describe('Navigation Accessibility', () => {
  test('skip link should be present and functional', async ({ page }) => {
    await page.goto('/')

    // Skip link should exist in DOM but be visually hidden
    const skipLink = page.locator('.skip-link')
    await expect(skipLink).toBeAttached()

    // Focus the skip link by tabbing
    await page.keyboard.press('Tab')

    // Verify skip link becomes visible when focused
    await expect(skipLink).toBeFocused()
    await expect(skipLink).toBeVisible()

    // Click skip link and verify focus moved to main content
    await skipLink.click()
    const mainContent = page.locator('#main-content')
    await expect(mainContent).toBeFocused()
  })

  test('skip link should work on all pages', async ({ page }) => {
    const paths = ['/', '/portfolio', '/history', '/analytics', '/settings']

    for (const path of paths) {
      await page.goto(path)

      // Skip link should exist
      const skipLink = page.locator('.skip-link')
      await expect(skipLink).toBeAttached()

      // Tab to focus skip link
      await page.keyboard.press('Tab')
      await expect(skipLink).toBeFocused()

      // Activate skip link
      await skipLink.click()

      // Main content should receive focus
      const mainContent = page.locator('#main-content')
      await expect(mainContent).toBeFocused()
    }
  })
})

test.describe('Navigation Active States - Header', () => {
  test('Dashboard nav link should be active on home page', async ({ page }) => {
    await page.goto('/')

    // Find header nav specifically
    const headerNav = page.locator('header nav[aria-label="Primary navigation"]')
    const dashboardLink = headerNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardLink).toHaveClass(/active/)

    // Verify other links are not active
    const portfolioLink = headerNav.getByRole('link', { name: 'Portfolio' })
    await expect(portfolioLink).not.toHaveClass(/active/)
  })

  test('Portfolio nav link should be active on portfolio page', async ({ page }) => {
    await page.goto('/portfolio')

    const headerNav = page.locator('header nav[aria-label="Primary navigation"]')
    const portfolioLink = headerNav.getByRole('link', { name: 'Portfolio' })
    await expect(portfolioLink).toHaveClass(/active/)

    const dashboardLink = headerNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardLink).not.toHaveClass(/active/)
  })

  test('History nav link should be active on history page', async ({ page }) => {
    await page.goto('/history')

    const headerNav = page.locator('header nav[aria-label="Primary navigation"]')
    const historyLink = headerNav.getByRole('link', { name: 'History' })
    await expect(historyLink).toHaveClass(/active/)

    const dashboardLink = headerNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardLink).not.toHaveClass(/active/)
  })

  test('Settings nav link should be active on settings page', async ({ page }) => {
    await page.goto('/settings')

    const headerNav = page.locator('header nav[aria-label="Primary navigation"]')
    const settingsLink = headerNav.getByRole('link', { name: 'Settings' })
    await expect(settingsLink).toHaveClass(/active/)

    const dashboardLink = headerNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardLink).not.toHaveClass(/active/)
  })
})

test.describe('Navigation Active States - Sidebar', () => {
  test('Dashboard sidebar item should be active on home page', async ({ page }) => {
    await page.goto('/')

    // Locate sidebar navigation item by ARIA label
    const sidebarNav = page.locator('aside nav[aria-label="Main navigation"]')
    const dashboardItem = sidebarNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardItem).toHaveClass(/active/)

    const portfolioItem = sidebarNav.getByRole('link', { name: 'Portfolio' })
    await expect(portfolioItem).not.toHaveClass(/active/)
  })

  test('Portfolio sidebar item should be active on portfolio page', async ({ page }) => {
    await page.goto('/portfolio')

    const sidebarNav = page.locator('aside nav[aria-label="Main navigation"]')
    const portfolioItem = sidebarNav.getByRole('link', { name: 'Portfolio' })
    await expect(portfolioItem).toHaveClass(/active/)

    const dashboardItem = sidebarNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardItem).not.toHaveClass(/active/)
  })

  test('History sidebar item should be active on history page', async ({ page }) => {
    await page.goto('/history')

    const sidebarNav = page.locator('aside nav[aria-label="Main navigation"]')
    const historyItem = sidebarNav.getByRole('link', { name: 'History' })
    await expect(historyItem).toHaveClass(/active/)

    const dashboardItem = sidebarNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardItem).not.toHaveClass(/active/)
  })

  test('Settings sidebar item should be active on settings page', async ({ page }) => {
    await page.goto('/settings')

    const sidebarNav = page.locator('aside nav[aria-label="Main navigation"]')
    const settingsItem = sidebarNav.getByRole('link', { name: 'Settings' })
    await expect(settingsItem).toHaveClass(/active/)

    const dashboardItem = sidebarNav.getByRole('link', { name: 'Dashboard' })
    await expect(dashboardItem).not.toHaveClass(/active/)
  })
})

test.describe('Navigation Visual Regression', () => {
  test('header navigation should match snapshot on all pages', async ({ page }) => {
    const pages = ['/', '/portfolio', '/history', '/analytics', '/settings']

    for (const path of pages) {
      await page.goto(path)

      // Screenshot just the header
      const header = page.locator('header')
      const snapshotName = path === '/' ? 'header-home.png' : `header-${path.slice(1)}.png`
      await expect(header).toHaveScreenshot(snapshotName)
    }
  })

  test('sidebar navigation should match snapshot on all pages', async ({ page }) => {
    const pages = ['/', '/portfolio', '/history', '/analytics', '/settings']

    for (const path of pages) {
      await page.goto(path)

      // Screenshot just the sidebar
      const sidebar = page.locator('aside')
      const snapshotName = path === '/' ? 'sidebar-home.png' : `sidebar-${path.slice(1)}.png`
      await expect(sidebar).toHaveScreenshot(snapshotName)
    }
  })
})
