import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Overline } from '../Overline'

afterEach(() => document.documentElement.removeAttribute('data-theme'))

describe('Overline', () => {
  it('renders its text', () => {
    render(<Overline>Overview</Overline>)
    expect(screen.getByText('Overview')).toBeInTheDocument()
  })

  it('is never a heading (must not enter the outline)', () => {
    render(<Overline as="p">Billing</Overline>)
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('renders a <span> by default and the requested element via `as`', () => {
    const { rerender } = render(<Overline>x</Overline>)
    expect(screen.getByText('x').tagName).toBe('SPAN')
    rerender(<Overline as="p">x</Overline>)
    expect(screen.getByText('x').tagName).toBe('P')
    rerender(<Overline as="dt">x</Overline>)
    expect(screen.getByText('x').tagName).toBe('DT')
  })

  it('takes the accent tone class when asked', () => {
    render(<Overline tone="accent">x</Overline>)
    expect(screen.getByText('x')).toHaveClass('text-accent-500')
  })

  it('renders under data-theme="light" without error', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    render(<Overline>Light</Overline>)
    expect(screen.getByText('Light')).toBeInTheDocument()
  })
})
