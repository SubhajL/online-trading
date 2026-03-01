import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'

type HelpDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const shortcuts = [
  { keys: ['Ctrl', 'K'], description: 'Command Palette' },
  { keys: ['Ctrl', 'B'], description: 'Toggle Sidebar' },
  { keys: ['Ctrl', '/'], description: 'Help' },
  { keys: ['Escape'], description: 'Close overlay' },
] as const

const glossaryTerms = [
  {
    term: 'CHOCH',
    description:
      'Change of Character — a shift in market structure indicating potential trend reversal.',
  },
  {
    term: 'BOS',
    description:
      'Break of Structure — continuation signal where price breaks a recent swing high or low.',
  },
  {
    term: 'Order Block',
    description:
      'The last opposing candle before a strong impulsive move, acting as a supply or demand zone.',
  },
  {
    term: 'FVG',
    description:
      'Fair Value Gap — an imbalance in price where a three-candle pattern leaves an unfilled gap.',
  },
  {
    term: 'EMA',
    description:
      'Exponential Moving Average — a weighted moving average that reacts faster to recent price changes.',
  },
  {
    term: 'RSI',
    description:
      'Relative Strength Index — a momentum oscillator measuring speed and magnitude of price changes (0-100).',
  },
  {
    term: 'MACD',
    description:
      'Moving Average Convergence Divergence — a trend-following indicator showing the relationship between two EMAs.',
  },
  {
    term: 'ATR',
    description:
      'Average True Range — a volatility indicator measuring the average range of price bars.',
  },
  {
    term: 'Bollinger Bands',
    description:
      'A volatility envelope set above and below a moving average using standard deviations.',
  },
] as const

export function HelpDrawer({ open, onOpenChange }: HelpDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[380px] sm:max-w-[380px]">
        <SheetHeader>
          <SheetTitle>Help</SheetTitle>
          <SheetDescription>Keyboard shortcuts, glossary, and app information.</SheetDescription>
        </SheetHeader>

        <Tabs defaultValue="shortcuts" className="mt-4">
          <TabsList className="w-full">
            <TabsTrigger value="shortcuts" className="flex-1">
              Shortcuts
            </TabsTrigger>
            <TabsTrigger value="glossary" className="flex-1">
              Glossary
            </TabsTrigger>
            <TabsTrigger value="about" className="flex-1">
              About
            </TabsTrigger>
          </TabsList>

          <TabsContent value="shortcuts">
            <ScrollArea className="h-[calc(100vh-220px)]">
              <div className="grid gap-3 py-3">
                {shortcuts.map(({ keys, description }) => (
                  <div key={description} className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{description}</span>
                    <span className="flex gap-1">
                      {keys.map(key => (
                        <kbd
                          key={key}
                          className="inline-flex h-6 min-w-6 items-center justify-center rounded border bg-muted px-1.5 text-xs font-medium"
                        >
                          {key}
                        </kbd>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="glossary">
            <ScrollArea className="h-[calc(100vh-220px)]">
              <div className="grid gap-3 py-3">
                {glossaryTerms.map(({ term, description }, index) => (
                  <div key={term}>
                    <dt className="text-sm font-medium">{term}</dt>
                    <dd className="mt-0.5 text-sm text-muted-foreground">{description}</dd>
                    {index < glossaryTerms.length - 1 && <Separator className="mt-3" />}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="about">
            <ScrollArea className="h-[calc(100vh-220px)]">
              <div className="grid gap-4 py-3">
                <div>
                  <h3 className="text-sm font-medium">Version</h3>
                  <p className="text-sm text-muted-foreground">0.1.0-dev</p>
                </div>
                <Separator />
                <div>
                  <h3 className="text-sm font-medium">Links</h3>
                  <ul className="mt-1 grid gap-1 text-sm text-muted-foreground">
                    <li>Documentation (coming soon)</li>
                    <li>Release Notes (coming soon)</li>
                  </ul>
                </div>
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
