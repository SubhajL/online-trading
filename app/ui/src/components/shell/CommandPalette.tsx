'use client'

import { useRouter } from 'next/navigation'
import {
  LayoutDashboard,
  Briefcase,
  TrendingUp,
  History,
  BarChart3,
  Settings,
  Plus,
  RefreshCw,
  Moon,
} from 'lucide-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { DialogTitle, DialogDescription } from '@/components/ui/dialog'

const NAV_ITEMS = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Portfolio', path: '/portfolio', icon: Briefcase },
  { label: 'Trading', path: '/trades', icon: TrendingUp },
  { label: 'History', path: '/history', icon: History },
  { label: 'Analytics', path: '/analytics', icon: BarChart3 },
  { label: 'Settings', path: '/settings', icon: Settings },
] as const

const ACTION_ITEMS = [
  { label: 'New Order', id: 'new-order', icon: Plus },
  { label: 'Refresh Data', id: 'refresh-data', icon: RefreshCw },
] as const

const THEME_ITEMS = [{ label: 'Toggle Dark Mode', id: 'toggle-dark-mode', icon: Moon }] as const

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
              <item.icon className="mr-2 h-4 w-4" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Actions">
          {ACTION_ITEMS.map(item => (
            <CommandItem key={item.id} onSelect={() => handleActionSelect(item.id)}>
              <item.icon className="mr-2 h-4 w-4" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Theme">
          {THEME_ITEMS.map(item => (
            <CommandItem key={item.id} onSelect={() => handleActionSelect(item.id)}>
              <item.icon className="mr-2 h-4 w-4" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
