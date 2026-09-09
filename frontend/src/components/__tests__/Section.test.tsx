import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { Section } from '../Section'

afterEach(() => document.documentElement.removeAttribute('data-theme'))

describe('Section', () => {
  it('renders the title as an h2 and the content', () => {
    render(
      <Section index="01" title="Team">
        <p>the roster</p>
      </Section>,
    )
    expect(
      screen.getByRole('heading', { level: 2, name: /Team/ }),
    ).toBeInTheDocument()
    expect(screen.getByText('the roster')).toBeInTheDocument()
  })

  it('the numeric index is decorative, not part of the heading', () => {
    render(
      <Section index="02" title="Plan">
        x
      </Section>,
    )
    expect(screen.getByText('02')).toHaveAttribute('aria-hidden', 'true')
  })

  it('renders an optional aside', () => {
    render(
      <Section index="01" title="Team" aside={<span>4 members</span>}>
        x
      </Section>,
    )
    expect(screen.getByText('4 members')).toBeInTheDocument()
  })

  it('renders under data-theme="light" without error', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    render(
      <Section index="03" title="Workspace">
        x
      </Section>,
    )
    expect(screen.getByRole('heading', { name: /Workspace/ })).toBeInTheDocument()
  })
})
