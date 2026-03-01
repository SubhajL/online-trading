import { chromium, FullConfig } from '@playwright/test'

async function globalTeardown(config: FullConfig) {
  console.log('🧹 Starting global test teardown...')

  const browser = await chromium.launch()
  const page = await browser.newPage()

  try {
    // Clean up test data if needed
    if (process.env.CLEANUP_TEST_DATA === 'true') {
      console.log('🗑️ Cleaning up test data...')
      
      const response = await page.request.delete('http://localhost:8002/api/test/cleanup')
      if (response.ok()) {
        console.log('✅ Test data cleaned up')
      } else {
        console.warn('⚠️ Failed to clean up test data:', response.status())
      }
    }

    // Generate test report summary
    console.log('📊 Generating test report summary...')
    
  } catch (error) {
    console.error('❌ Global teardown failed:', error)
    // Don't throw - teardown failures shouldn't fail the test run
  } finally {
    await browser.close()
  }

  console.log('✅ Global teardown completed')
}

export default globalTeardown
