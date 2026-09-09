import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Readout } from '../Readout'

afterEach(() => document.documentElement.removeAttribute('data-theme'))

const ITEMS = [
  { value: 'Active', tone: 'success' as const },
  { value: 'US$49.00 / month' },
  { value: 'in 12 days' },
]

describe('Readout', () => {
  it('renders every figure', () => {
    render(<Readout items={ITEMS} />)
    for (const item of ITEMS) {
      expect(screen.getByText(item.value)).toBeInTheDocument()
    }
  })

  it('a status dot is decorative (aria-hidden); the word carries the meaning', () => {
    const { container } = render(<Readout items={ITEMS} />)
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(
      container.querySelector('.rounded-full[aria-hidden="true"]'),
    ).not.toBeNull()
  })

  it('items without a tone render no dot', () => {
    const { container } = render(<Readout items={[{ value: 'in 12 days' }]} />)
    expect(
      container.querySelector('.rounded-full[aria-hidden="true"]'),
    ).toBeNull()
  })

  it('renders under data-theme="light" without error', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    render(<Readout items={ITEMS} />)
    expect(screen.getByText('in 12 days')).toBeInTheDocument()
  })
})
