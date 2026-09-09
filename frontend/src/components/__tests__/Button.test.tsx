import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button, type ButtonVariant } from '../Button'

describe('Button', () => {
  it('keeps the label mounted (hidden) while loading so width cannot shift', () => {
    const { rerender } = render(<Button>Save changes</Button>)
    const restingLabel = screen.getByText('Save changes')
    expect(restingLabel).toBeVisible()

    rerender(<Button loading>Save changes</Button>)
    const loadingLabel = screen.getByText('Save changes')
    // Still in the DOM — only visually hidden. This is the mechanism that
    // guarantees no layout shift (jsdom has no layout engine to measure).
    expect(loadingLabel).toBeInTheDocument()
    expect(loadingLabel).toHaveClass('invisible')
    expect(loadingLabel).toHaveAttribute('aria-hidden', 'true')
  })

  it('exposes aria-busy and a loading announcement while loading', () => {
    render(<Button loading>Save</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Loading')).toBeInTheDocument()
  })

  it('does not fire onClick when disabled', async () => {
    const onClick = vi.fn()
    render(
      <Button disabled onClick={onClick}>
        Delete
      </Button>,
    )
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('does not fire onClick when loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Delete
      </Button>,
    )
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('renders every variant', () => {
    const variants: ButtonVariant[] = ['primary', 'secondary', 'ghost', 'danger']
    for (const variant of variants) {
      const { unmount } = render(<Button variant={variant}>{variant}</Button>)
      expect(screen.getByRole('button', { name: variant })).toBeInTheDocument()
      unmount()
    }
  })

  it('ghost variant carries a visible border by default, not only on hover', () => {
    render(<Button variant="ghost">Cancel</Button>)
    // §C.1a fix: the border must be present in the resting class list, not
    // gated behind a hover: prefix.
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass(
      'border',
      'border-subtle',
    )
  })

  it('defaults to type="button"', () => {
    render(<Button>Go</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
})
