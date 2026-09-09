import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert, type AlertVariant } from '../Alert'

describe('Alert', () => {
  it('renders its body and an optional title', () => {
    render(<Alert title="Heads up">Something to know.</Alert>)
    expect(screen.getByText('Heads up')).toBeInTheDocument()
    expect(screen.getByText('Something to know.')).toBeInTheDocument()
  })

  it('is assertive (role="alert") for danger, polite (role="status") otherwise', () => {
    const { rerender } = render(<Alert variant="danger">Failed.</Alert>)
    expect(screen.getByRole('alert')).toHaveTextContent('Failed.')

    rerender(<Alert variant="info">FYI.</Alert>)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('FYI.')
  })

  it('honours an explicit assertive override', () => {
    render(
      <Alert variant="warning" assertive>
        Act now.
      </Alert>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('renders every variant', () => {
    const variants: AlertVariant[] = ['info', 'success', 'warning', 'danger']
    for (const variant of variants) {
      const { unmount } = render(<Alert variant={variant}>{variant}</Alert>)
      expect(screen.getByText(variant)).toBeInTheDocument()
      unmount()
    }
  })
})
