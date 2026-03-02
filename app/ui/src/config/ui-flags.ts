function parseBooleanFlag(value: string | undefined): boolean {
  if (!value) return false
  const normalized = value.trim().toLowerCase()
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
}

export function isUiRevampEnabled(): boolean {
  return parseBooleanFlag(process.env.NEXT_PUBLIC_UI_REVAMP)
}
