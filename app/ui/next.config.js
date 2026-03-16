/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ['lightweight-charts'],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3001',
    NEXT_INTERNAL_API_URL: process.env.NEXT_INTERNAL_API_URL || 'http://bff:3001/api',
  },
  async rewrites() {
    const internalApiUrl = process.env.NEXT_INTERNAL_API_URL || 'http://bff:3001/api'
    return [
      {
        source: '/api/:path*',
        destination: `${internalApiUrl}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
