/**
 * Design Tokens Type Definitions
 * Mirrors the CSS custom property structure from tokens.css
 */

export type ColorScale = Record<50 | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900, string>

export type SurfaceColors = {
  base: string
  raised: string
  overlay: string
  hover: string
  input: string
}

export type TextColors = {
  primary: string
  secondary: string
  muted: string
  disabled: string
  inverse: string
  success: string
  danger: string
  warning: string
  info: string
}

export type BorderColors = {
  subtle: string
  default: string
  strong: string
  focus: string
}

export type SpacingScale = Record<0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10, string>

export type RadiusScale = {
  none: string
  sm: string
  md: string
  lg: string
  full: string
}

export type Typography = {
  fontSize: {
    xs: string
    sm: string
    base: string
    lg: string
    xl: string
    '2xl': string
    '3xl': string
    '4xl': string
    '5xl': string
  }
  fontWeight: {
    normal: number
    medium: number
    semibold: number
    bold: number
  }
  lineHeight: {
    tight: number
    normal: number
    relaxed: number
  }
}

export type ChartColors = {
  bg: string
  text: string
  grid: string
  candleUp: string
  candleDown: string
}

export type Breakpoints = {
  mobile: string
  tablet: string
  desktop: string
  wide: string
}

export type Constraints = {
  maxScrollHeight: string
  minTouchTarget: string
}

export interface DesignTokens {
  colors: {
    primary: ColorScale
    success: ColorScale
    warning: ColorScale
    error: ColorScale
    info: ColorScale
    gray: ColorScale
    surface: SurfaceColors
    text: TextColors
    border: BorderColors
  }
  spacing: SpacingScale
  radius: RadiusScale
  typography: Typography
  chart: ChartColors
  breakpoints: Breakpoints
  constraints: Constraints
}
