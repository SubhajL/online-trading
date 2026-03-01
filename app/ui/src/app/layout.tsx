import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { SkipLink } from '@/components/common/SkipLink'
import { ToastStack } from '@/components/shell'
import { Providers } from './providers'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'Trading Platform',
  description: 'Professional cryptocurrency trading platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
        />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans`}>
        <SkipLink />
        <Providers>
          {children}
          <ToastStack />
        </Providers>
      </body>
    </html>
  )
}
