import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Button } from '../Button'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders the headline and description', () => {
    render(
      <EmptyState
        headline="No webhook events yet"
        description="Events appear here once Stripe starts sending them."
      />,
    )
    expect(
      screen.getByRole('heading', { name: 'No webhook events yet' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Events appear here once Stripe starts sending them.'),
    ).toBeInTheDocument()
  })

  it('shows a default glyph so the panel is never blank', () => {
    const { container } = render(
      <EmptyState headline="Nothing here" description="Empty." />,
    )
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders the action only when one is provided', () => {
    const { rerender } = render(
      <EmptyState headline="No members" description="Invite a teammate." />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()

    rerender(
      <EmptyState
        headline="No members"
        description="Invite a teammate."
        action={<Button size="sm">Invite member</Button>}
      />,
    )
    expect(
      screen.getByRole('button', { name: 'Invite member' }),
    ).toBeInTheDocument()
  })
})
