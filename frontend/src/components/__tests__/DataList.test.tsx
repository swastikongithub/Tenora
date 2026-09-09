import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { DataList } from '../DataList'

afterEach(() => document.documentElement.removeAttribute('data-theme'))

describe('DataList', () => {
  it('renders each row as a term / value pair', () => {
    render(
      <DataList
        rows={[
          { term: 'Plan', children: 'PRO' },
          { term: 'Price', children: 'US$49.00' },
        ]}
      />,
    )
    expect(screen.getByText('Plan')).toBeInTheDocument()
    expect(screen.getByText('PRO')).toBeInTheDocument()
    expect(screen.getByText('Price')).toBeInTheDocument()
    expect(screen.getByText('US$49.00')).toBeInTheDocument()
  })

  it('uses real dl / dt / dd semantics', () => {
    const { container } = render(
      <DataList rows={[{ term: 'Slug', children: 'demo-workspace' }]} />,
    )
    expect(container.querySelector('dl > div > dt')).not.toBeNull()
    expect(container.querySelector('dl > div > dd')).not.toBeNull()
  })

  it('renders no heading (it is a spec-sheet, not a section)', () => {
    render(<DataList rows={[{ term: 'Name', children: 'Demo Workspace' }]} />)
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('renders under data-theme="light" without error', () => {
    document.documentElement.setAttribute('data-theme', 'light')
    render(<DataList rows={[{ term: 'Name', children: 'Demo Workspace' }]} />)
    expect(screen.getByText('Demo Workspace')).toBeInTheDocument()
  })
})
