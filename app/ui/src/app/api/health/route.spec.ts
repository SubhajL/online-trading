import { describe, expect, it } from 'vitest'

import { GET } from './route'

describe('GET /api/health', () => {
  it('returns 200 with ok status and a parseable ISO timestamp', async () => {
    const response = GET()

    expect(response.status).toBe(200)
    const body = await response.json()
    expect(body).toEqual({ status: 'ok', timestamp: expect.any(String) })
    expect(new Date(body.timestamp).toISOString()).toBe(body.timestamp)
  })
})
