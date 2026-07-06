'use client'

import { useRouter } from 'next/navigation'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { MaterialIcon } from '@/components/common/MaterialIcon'

const NAV_ITEMS = [
  { label: 'Dashboard', path: '/', icon: 'dashboard' },
  { label: 'Portfolio', path: '/portfolio', icon: 'work' },
  { label: 'Trading', path: '/trades', icon: 'candlestick_chart' },
  { label: 'History', path: '/history', icon: 'history' },
  { label: 'Analytics', path: '/analytics', icon: 'bar_chart' },
  { label: 'Soak', path: '/soak', icon: 'monitor_heart' },
  { label: 'Settings', path: '/settings', icon: 'settings' },
] as const

const ACTION_ITEMS = [
  { label: 'New Order', id: 'new-order', icon: 'add' },
  { label: 'Refresh Data', id: 'refresh-data', icon: 'refresh' },
] as const

const THEME_ITEMS = [
  { label: 'Toggle Dark Mode', id: 'toggle-dark-mode', icon: 'dark_mode' },
] as const

type CommandPaletteProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter()

  function handleNavSelect(path: string) {
    router.push(path)
    onOpenChange(false)
  }

  function handleActionSelect(id: string) {
    // Action handlers can be extended via props or context
    void id
    onOpenChange(false)
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="sr-only">Command Palette</DialogTitle>
      <DialogDescription className="sr-only">Search for commands and navigation</DialogDescription>
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigation">
          {NAV_ITEMS.map(item => (
            <CommandItem key={item.path} onSelect={() => handleNavSelect(item.path)}>
              <MaterialIcon name={item.icon} size="md" className="mr-2" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Actions">
          {ACTION_ITEMS.map(item => (
            <CommandItem key={item.id} onSelect={() => handleActionSelect(item.id)}>
              <MaterialIcon name={item.icon} size="md" className="mr-2" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Theme">
          {THEME_ITEMS.map(item => (
            <CommandItem key={item.id} onSelect={() => handleActionSelect(item.id)}>
              <MaterialIcon name={item.icon} size="md" className="mr-2" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
