import { chromium, FullConfig } from '@playwright/test'

async function globalSetup(config: FullConfig) {
  console.log('🚀 Starting global test setup...')

  // Create a browser instance for setup
  const browser = await chromium.launch()
  const page = await browser.newPage()

  try {
    // Wait for services to be ready
    console.log('⏳ Waiting for services to be ready...')
    
    // Check UI service
    await page.goto(config.projects[0].use.baseURL || 'http://localhost:3000', {
      waitUntil: 'networkidle',
      timeout: 60000,
    })
    console.log('✅ UI service is ready')

    // Check BFF service
    const bffResponse = await page.request.get('http://localhost:8002/api/health')
    if (!bffResponse.ok()) {
      throw new Error(`BFF service not ready: ${bffResponse.status()}`)
    }
    console.log('✅ BFF service is ready')

    // Seed test data if needed
    if (process.env.SEED_TEST_DATA === 'true') {
      console.log('🌱 Seeding test data...')
      await seedTestData(page)
      console.log('✅ Test data seeded')
    }

    // Create admin auth state for admin tests
    await createAdminAuthState(page)
    console.log('✅ Admin auth state created')

  } catch (error) {
    console.error('❌ Global setup failed:', error)
    throw error
  } finally {
    await browser.close()
  }

  console.log('✅ Global setup completed')
}

async function seedTestData(page: any) {
  // Seed test orders, positions, etc.
  const testData = {
    orders: [
      {
        id: 'test-order-1',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: '0.001',
        status: 'FILLED',
        price: '42000.00',
        timestamp: new Date().toISOString(),
      },
      {
        id: 'test-order-2',
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: '0.1',
        status: 'PENDING',
        price: '3000.00',
        timestamp: new Date().toISOString(),
      },
    ],
    positions: [
      {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: '0.001',
        entryPrice: '42000.00',
        unrealizedPnl: '50.00',
        timestamp: new Date().toISOString(),
      },
    ],
  }

  // Send test data to BFF
  await page.request.post('http://localhost:8002/api/test/seed', {
    data: testData,
  })
}

async function createAdminAuthState(page: any) {
  // Create admin authentication state for admin tests
  await page.goto('http://localhost:3000/admin/login')
  
  // Fill admin credentials (if login page exists)
  const usernameInput = page.locator('input[name="username"]')
  if (await usernameInput.isVisible({ timeout: 5000 })) {
    await usernameInput.fill('admin')
    await page.locator('input[name="password"]').fill('admin123')
    await page.locator('button[type="submit"]').click()
    
    // Save admin auth state
    await page.context().storageState({ path: 'tests/auth/admin-auth.json' })
  }
}

export default globalSetup
