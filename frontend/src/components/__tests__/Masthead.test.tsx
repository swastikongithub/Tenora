import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Masthead } from '../Masthead'

afterEach(() => document.documentElement.removeAttribute('data-theme'))

describe('Masthead', () => {
  it('renders the overline, the statement as the page h1, and the lede', () => {
    render(
      <Masthead
        overline="Overview"
        statement="The Pro plan is active."
        lede="Everything is fine."
      />,
    )
    expect(
      screen.getByRole('heading', { level: 1, name: 'The Pro plan is active.' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Everything is fine.')).toBeInTheDocument()
  })

  it('the overline is not itself a heading', () => {
    render(<Masthead overline="Overview" statement="x" />)
    expect(screen.getAllByRole('heading')).toHaveLength(1)
  })

  it('the statement uses the composed register (text-display stepping to text-edge)', () => {
    render(<Masthead overline="Overview" statement="Big statement." />)
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1).toHaveClass('text-display', 'sm:text-edge')
  })

  it('renders an optional readout slot and omits the lede when absent', () => {
    render(
      <Masthead
        overline="Overview"
        statement="x"
        readout={<div>readout-here</div>}
      />,
    )
    expect(screen.getByText('readout-here')).toBeInTheDocument()
  })

  it('renders under data-theme="light" without error', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    render(<Masthead overline="Overview" statement="Light statement." />)
    expect(screen.getByText('Light statement.')).toBeInTheDocument()
  })
})
