import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Badge, type BadgeVariant } from '../Badge'

describe('Badge', () => {
  it('always renders a readable text label', () => {
    render(<Badge variant="success">ACTIVE</Badge>)
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
  })

  it('renders every variant with its label', () => {
    const variants: BadgeVariant[] = [
      'success',
      'warning',
      'danger',
      'neutral',
      'accent',
    ]
    for (const variant of variants) {
      const { unmount } = render(<Badge variant={variant}>{variant}</Badge>)
      expect(screen.getByText(variant)).toBeInTheDocument()
      unmount()
    }
  })

  it('throws when given no visible label (color alone is not allowed, §C.8)', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Badge>{''}</Badge>)).toThrow(/visible text label/)
    expect(() => render(<Badge>{null}</Badge>)).toThrow(/visible text label/)
    expect(() => render(<Badge>{'   '}</Badge>)).toThrow(/visible text label/)
    spy.mockRestore()
  })
})
