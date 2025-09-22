import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Set environment variables for tests
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8002/api'
process.env.NEXT_PUBLIC_WS_URL = 'ws://localhost:8002'

afterEach(() => {
  cleanup()
})
