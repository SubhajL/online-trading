import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { SkipLink } from '@/components/common/SkipLink'
import { ToastStack } from '@/components/shell'
import { Providers } from './providers'
import './globals.css'
import '../styles/tokens.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Trading Platform',
  description: 'Professional cryptocurrency trading platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <SkipLink />
        <Providers>
          {children}
          <ToastStack />
        </Providers>
      </body>
    </html>
  )
}
