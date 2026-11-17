import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { clsx } from 'clsx'
import { X } from 'lucide-react'
import { useLayoutEffect, useRef, type ComponentProps, type ReactNode } from 'react'

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  /** `wide`: the Help centre and the tour, which hold a walkthrough beside their text. */
  size?: 'md' | 'wide'
}

/** The control that opened a dialog, focused again when it closes (by Escape, Cancel or the close button): our
 *  dialogs are opened from state, not from a Radix trigger, so Radix alone would leave focus on the page body. */
function useReturnFocus(open: boolean) {
  const opener = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    if (open && document.activeElement instanceof HTMLElement && document.activeElement !== document.body) opener.current = document.activeElement
  }, [open])
  return (event: Event) => {
    const target = opener.current
    opener.current = null
    if (target?.isConnected) {
      event.preventDefault()
      target.focus()
    }
  }
}

export function Dialog({ open, onOpenChange, title, description, children, footer, size = 'md' }: DialogProps) {
  const returnFocus = useReturnFocus(open)
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-scrim backdrop-blur-[2px]" />
        <DialogPrimitive.Content onCloseAutoFocus={returnFocus} className={clsx('fixed inset-x-4 top-1/2 z-50 mx-auto max-h-[90vh] -translate-y-1/2 overflow-y-auto rounded-2xl bg-surface p-6 shadow-raised focus:outline-none', size === 'wide' ? 'max-w-3xl' : 'max-w-md')}>
          <DialogPrimitive.Title className="pr-8 text-lg font-semibold">{title}</DialogPrimitive.Title>
          {description && <DialogPrimitive.Description className="mt-2 text-sm text-fg-muted">{description}</DialogPrimitive.Description>}
          {children && <div className="mt-4">{children}</div>}
          {footer && <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{footer}</div>}
          <DialogPrimitive.Close className="absolute top-4 right-4 rounded-md p-1.5 text-fg-subtle hover:bg-surface-muted hover:text-fg" aria-label="Close">
            <X className="size-4" />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function Drawer({ open, onOpenChange, title, children }: Omit<DialogProps, 'footer' | 'description'>) {
  const returnFocus = useReturnFocus(open)
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-scrim" />
        <DialogPrimitive.Content onCloseAutoFocus={returnFocus} className="fixed inset-y-0 right-0 z-50 flex w-[min(20rem,85vw)] flex-col bg-surface shadow-raised focus:outline-none">
          <div className="flex h-16 items-center justify-between border-b border-line px-4">
            <DialogPrimitive.Title className="text-sm font-semibold text-fg-muted">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="rounded-md p-2 text-fg-subtle hover:bg-surface-muted hover:text-fg" aria-label="Close menu">
              <X className="size-5" />
            </DialogPrimitive.Close>
          </div>
          <DialogPrimitive.Description className="sr-only">Site navigation</DialogPrimitive.Description>
          <div className="flex-1 overflow-y-auto p-4">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export const Tabs = TabsPrimitive.Root

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={clsx('-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0', className)}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={clsx(
        '-mb-px inline-flex shrink-0 items-center gap-2 border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-fg-muted transition-colors hover:text-fg',
        'data-[state=active]:border-brand-600 data-[state=active]:text-brand-800',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={clsx('pt-6 focus-visible:outline-none', className)} {...props} />
}
