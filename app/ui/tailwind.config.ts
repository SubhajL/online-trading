import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'chart-bg': '#161a1e',
        'chart-text': '#d1d4dc',
        'chart-grid': '#2a2e39',
        'success': '#26a69a',
        'danger': '#ef5350',
        'primary': '#2962ff',
        'secondary': '#ff6e40',
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      }
    },
  },
  plugins: [],
}

export default config