import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PlatformBarChart } from '../PlatformBarChart'

describe('PlatformBarChart', () => {
  it('renders a visible label AND numeric value for every bar (never colour-only)', () => {
    render(
      <PlatformBarChart
        title="By plan"
        data={[
          { label: 'Pro', value: 4 },
          { label: 'Team', value: 1 },
          { label: 'Free', value: 0 },
        ]}
      />,
    )

    const chart = screen.getByRole('img', { name: /by plan/i })
    // Each label and each value is present as real text in the SVG.
    for (const label of ['Pro', 'Team', 'Free']) {
      expect(within(chart).getByText(label)).toBeInTheDocument()
    }
    expect(within(chart).getByText('4')).toBeInTheDocument()
    expect(within(chart).getByText('1')).toBeInTheDocument()
    expect(within(chart).getByText('0')).toBeInTheDocument()
  })

  it('includes every datum in the accessible summary', () => {
    render(
      <PlatformBarChart
        title="By status"
        data={[
          { label: 'Active', value: 2 },
          { label: 'Canceled', value: 5 },
        ]}
      />,
    )
    expect(
      screen.getByRole('img', { name: 'By status: Active 2, Canceled 5' }),
    ).toBeInTheDocument()
  })

  it('shows an explicit empty message instead of an empty chart when there is no data', () => {
    render(<PlatformBarChart title="Signups" data={[]} emptyLabel="No signups yet." />)

    expect(screen.getByText('No signups yet.')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('treats an all-zero data set as empty', () => {
    render(
      <PlatformBarChart
        title="Signups"
        data={[
          { label: 'Jan', value: 0 },
          { label: 'Feb', value: 0 },
        ]}
      />,
    )
    expect(screen.getByText('No data yet.')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
